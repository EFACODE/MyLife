"""Open Finance connector — Pierre Finance (T4.9).

Pulls already-aggregated accounts and transactions from the Pierre Finance API
(https://docs.pierre.finance) and imports them via the T3.4 connector
contract, mirroring the bank CSV connector (T4.2) but as a *pull* rather than
a file upload: Pierre has no "connect a bank account" endpoint — the user
links banks inside Pierre's own product (WhatsApp flow or
``pierre.finance/connect``) — so this connector only reads back what Pierre
has already aggregated, authenticated with a per-user API key held in the
``CredentialVault`` (T4.9's identity spec).

See ``specs/domain/finance/openfinance-connector.md`` for the full design,
including the (flagged, best-effort) mapping of Pierre's ``Transaction`` JSON
shape: Pierre's own published OpenAPI spec leaves that schema empty (``{}``),
so the field names tried below are inferred from cross-references elsewhere
in its docs, not confirmed against a live response. Raw payloads are stored
verbatim regardless (see the spec's §7/§9), so a wrong guess here loses no
data — it only fails the affected row loudly (``ValueError``) instead of
importing something wrong.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from mylife.connectors.base import FetchContext, RawPayload
from mylife.core.events import LifeEvent, StoredRawRecord
from mylife.core.events.envelope import ensure_utc
from mylife.finance.models import (
    FinancePayload,
    OpenFinanceTransactionImported,
    PositionPayload,
    PositionValued,
)
from mylife.finance.service import FinanceService
from mylife.identity.credential_vault import CredentialVault

OPENFINANCE_SOURCE = "openfinance"
PIERRE_PROVIDER = "pierre_finance"

# Best-effort field names for Pierre's undocumented ``Transaction`` shape (see
# module docstring). Tried in order; the first present value wins.
_DATE_FIELDS = ("date", "postDate", "transactionDate")
_DESCRIPTION_FIELDS = ("description", "merchantName", "memo")
_ID_FIELDS = ("id", "transactionId")


class MissingCredentialError(Exception):
    """Raised when a user has no API key stored for a provider."""

    def __init__(self, user_id: uuid.UUID, provider: str) -> None:
        super().__init__(f"no {provider!r} credential stored for user {user_id}")
        self.user_id = user_id
        self.provider = provider


class PierreApiError(Exception):
    """Raised when the Pierre Finance API returns an error response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"Pierre Finance API error {status_code}: {message}")
        self.status_code = status_code


def _to_minor_units(amount: float) -> int:
    """Convert a decimal-reais amount (e.g. ``150.00``) to integer minor units.

    Pierre returns amounts as floats, never minor units (unlike this
    codebase's own convention). Goes through ``Decimal(str(...))`` rather than
    ``round(amount * 100)`` to avoid binary float rounding artifacts on money
    (T4.9 spec FR-5). Assumes 2 decimal places (correct for BRL; see the
    spec's §9 on the multi-currency limitation).
    """
    try:
        return int((Decimal(str(amount)) * 100).to_integral_value())
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount {amount!r}") from exc


def _first_present(row: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return None


def _parse_transaction_date(value: str) -> datetime:
    """Parse a Pierre date string, treating a naive result as UTC.

    Unlike the CSV connectors' ``occurred_at`` (which requires an explicit UTC
    offset by contract), Pierre's date format is not documented and is likely
    a bare ``YYYY-MM-DD`` with no timezone — so a naive parse is assumed UTC
    rather than rejected.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid transaction date {value!r}") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _account_external_id(account: dict[str, Any]) -> str:
    value = account.get("accountId")
    if not value:
        raise ValueError("Pierre account missing 'accountId'")
    return str(value)


def _account_currency(account: dict[str, Any]) -> str:
    value = account.get("accountCurrencyCode")
    if not value:
        raise ValueError("Pierre account missing 'accountCurrencyCode'")
    return str(value).strip().upper()


def _account_name(account: dict[str, Any]) -> str:
    name = account.get("accountMarketingName") or account.get("accountName")
    return str(name) if name else "Open Finance account"


class PierreFinanceClient:
    """Thin client for the Pierre Finance endpoints this connector needs.

    See https://docs.pierre.finance. Takes an injectable ``httpx.Client`` so
    tests run against ``httpx.MockTransport`` — no real network call.
    """

    def __init__(self, *, base_url: str, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(base_url=base_url, timeout=30.0)

    def _get(self, path: str, api_key: str, *, params: dict[str, str] | None = None) -> Any:
        try:
            response = self._client.get(
                path, headers={"Authorization": f"Bearer {api_key}"}, params=params
            )
        except httpx.HTTPError as exc:
            raise PierreApiError(502, str(exc)) from exc
        if response.status_code >= 400:
            raise PierreApiError(response.status_code, response.text)
        body = response.json()
        if body.get("success") is False:
            raise PierreApiError(response.status_code, str(body.get("error", body)))
        return body

    def get_accounts(self, api_key: str) -> list[dict[str, Any]]:
        """Return the user's accounts (``GET /tools/api/get-accounts``)."""
        body = self._get("/tools/api/get-accounts", api_key)
        return list(body.get("data") or [])

    def get_transactions(
        self, api_key: str, *, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """Return settled transactions in ``[start_date, end_date]``.

        Only ``POSTED`` transactions are requested — see the spec's §9 on why
        ``PENDING`` rows (which can still change) are excluded from v1.
        """
        body = self._get(
            "/tools/api/get-transactions",
            api_key,
            params={
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "includeStatus": "POSTED",
                "format": "raw",
            },
        )
        return list(body.get("data") or [])


class PierreFinanceConnector:
    """Pulls accounts + transactions from Pierre Finance for one user's sync.

    Needs only ``(source, user_id)`` at sync time (the API key comes from the
    vault, not a per-request upload) — unlike the CSV connectors, so it could
    later be registered on the shared connector registry for scheduled runs
    (deferred, see the spec's §9).
    """

    source = OPENFINANCE_SOURCE

    def __init__(
        self,
        finance: FinanceService,
        vault: CredentialVault,
        client: PierreFinanceClient,
        *,
        now: datetime,
        lookback_days: int = 30,
    ) -> None:
        self._finance = finance
        self._vault = vault
        self._client = client
        self._now = ensure_utc(now)
        self._lookback_days = lookback_days

    def fetch(self, context: FetchContext) -> Iterable[RawPayload]:
        api_key = self._vault.get(context.user_id, PIERRE_PROVIDER)
        if api_key is None:
            raise MissingCredentialError(context.user_id, PIERRE_PROVIDER)

        accounts = self._client.get_accounts(api_key)
        account_ids: dict[str, uuid.UUID] = {}
        account_currencies: dict[str, str] = {}
        balance_payloads: list[RawPayload] = []

        for account in accounts:
            external_id = _account_external_id(account)
            currency = _account_currency(account)
            linked = self._finance.get_or_create_external_account(
                context.user_id,
                OPENFINANCE_SOURCE,
                external_id,
                name=_account_name(account),
                currency=currency,
                now=self._now,
            )
            account_ids[external_id] = linked.account_id
            account_currencies[external_id] = currency
            balance_payloads.append(
                RawPayload(
                    content={
                        "kind": "balance",
                        "mylife_account_id": str(linked.account_id),
                        "currency": currency,
                        "balance": account.get("accountBalance"),
                    },
                    fetched_at=self._now,
                )
            )

        end_date = self._now.date()
        start_date = end_date - timedelta(days=self._lookback_days)
        transactions = self._client.get_transactions(
            api_key, start_date=start_date, end_date=end_date
        )
        transaction_payloads: list[RawPayload] = []
        for row in transactions:
            raw_account_id = row.get("accountId")
            mylife_account_id = account_ids.get(str(raw_account_id)) if raw_account_id else None
            if mylife_account_id is None:
                # A transaction for an account not in get-accounts (e.g.
                # closed/filtered since) — skip rather than guess.
                continue
            transaction_external_id = _first_present(row, _ID_FIELDS)
            transaction_payloads.append(
                RawPayload(
                    content={
                        "kind": "transaction",
                        "mylife_account_id": str(mylife_account_id),
                        "account_currency": account_currencies[str(raw_account_id)],
                        "raw": row,
                    },
                    fetched_at=self._now,
                    external_id=str(transaction_external_id) if transaction_external_id else None,
                )
            )
        # Transactions first, balance marks last: net worth (T4.3) treats a
        # `PositionValued` as an absolute reset, so Pierre's own current
        # balance — the ground truth — must be the last event appended each
        # sync, superseding the running transaction sum rather than adding to
        # it (which would double-count, since that balance already reflects
        # every transaction up to now).
        return transaction_payloads + balance_payloads

    def normalize(self, raw: StoredRawRecord) -> Iterable[LifeEvent[Any]]:
        content: Any = raw.content
        kind = content.get("kind")
        if kind == "balance":
            yield PositionValued(
                user_id=raw.user_id,
                occurred_at=raw.fetched_at,
                source=self.source,
                correlation_id=raw.correlation_id,
                raw_record_id=raw.raw_record_id,
                payload=PositionPayload(
                    account_id=uuid.UUID(content["mylife_account_id"]),
                    value_minor=_to_minor_units(float(content["balance"])),
                    currency=str(content["currency"]),
                ),
            )
            return
        if kind != "transaction":
            raise ValueError(f"unknown openfinance raw payload kind {kind!r}")

        row: dict[str, Any] = content["raw"]
        amount = row.get("amount")
        if amount is None:
            raise ValueError("openfinance transaction missing 'amount'")
        description = _first_present(row, _DESCRIPTION_FIELDS)
        if not description:
            raise ValueError("openfinance transaction missing a recognized description field")
        occurred_raw = _first_present(row, _DATE_FIELDS)
        if not occurred_raw:
            raise ValueError("openfinance transaction missing a recognized date field")
        external_id = _first_present(row, _ID_FIELDS)
        category = row.get("category")

        yield OpenFinanceTransactionImported(
            user_id=raw.user_id,
            occurred_at=_parse_transaction_date(str(occurred_raw)),
            source=self.source,
            correlation_id=raw.correlation_id,
            raw_record_id=raw.raw_record_id,
            payload=FinancePayload(
                account_id=uuid.UUID(content["mylife_account_id"]),
                amount_minor=_to_minor_units(float(amount)),
                currency=str(content["account_currency"]),
                description=str(description),
                category=str(category) if category is not None else None,
                external_id=str(external_id) if external_id else None,
            ),
        )
