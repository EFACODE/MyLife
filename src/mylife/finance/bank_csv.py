"""Bank CSV connector (T4.2).

Imports bank statement rows into finance as ``TransactionImported`` events
(T4.1) against one of the user's accounts, implementing the T3.4 ``Connector``
contract with no new dependency. Consent-gated on ``source = "bank"`` when run
through the connector runner. See ``specs/domain/finance/bank-connector.md``.

CSV columns: ``amount_minor`` (signed int), ``occurred_at`` (ISO-8601 UTC) and
``description`` required; ``currency`` (defaults to the account's), ``category``
and ``external_id`` optional.
"""

import csv
import io
import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from mylife.connectors.base import FetchContext, RawPayload
from mylife.core.events import LifeEvent, StoredRawRecord
from mylife.core.events.envelope import ensure_utc
from mylife.finance.models import FinancePayload, TransactionImported

BANK_SOURCE = "bank"
_REQUIRED_FIELDS = ("amount_minor", "occurred_at", "description")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid occurred_at {value!r}") from exc
    return ensure_utc(parsed)


def _parse_amount(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"invalid amount_minor {value!r}") from exc


class BankCsvConnector:
    """Imports bank transactions from CSV text against a target account."""

    source = BANK_SOURCE

    def __init__(
        self,
        csv_text: str,
        *,
        account_id: uuid.UUID,
        account_currency: str,
        fetched_at: datetime,
    ) -> None:
        self._csv_text = csv_text
        self._account_id = account_id
        self._account_currency = account_currency.strip().upper()
        self._fetched_at = ensure_utc(fetched_at)

    def fetch(self, context: FetchContext) -> Iterable[RawPayload]:
        reader = csv.DictReader(io.StringIO(self._csv_text))
        payloads: list[RawPayload] = []
        for row in reader:
            external_id = (row.get("external_id") or "").strip() or None
            content = {
                "amount_minor": (row.get("amount_minor") or "").strip(),
                "occurred_at": (row.get("occurred_at") or "").strip(),
                "description": (row.get("description") or "").strip(),
                "currency": (row.get("currency") or "").strip() or None,
                "category": (row.get("category") or "").strip() or None,
                "external_id": external_id,
            }
            payloads.append(
                RawPayload(content=content, fetched_at=self._fetched_at, external_id=external_id)
            )
        return payloads

    def normalize(self, raw: StoredRawRecord) -> Iterable[LifeEvent[Any]]:
        content: Any = raw.content
        for field in _REQUIRED_FIELDS:
            if not content.get(field):
                raise ValueError(f"missing required bank field {field!r}")
        currency = (content.get("currency") or self._account_currency).strip().upper()
        if currency != self._account_currency:
            raise ValueError(
                f"row currency {currency!r} does not match account "
                f"currency {self._account_currency!r}"
            )
        yield TransactionImported(
            user_id=raw.user_id,
            occurred_at=_parse_utc(content["occurred_at"]),
            source=self.source,
            correlation_id=raw.correlation_id,
            raw_record_id=raw.raw_record_id,
            payload=FinancePayload(
                account_id=self._account_id,
                amount_minor=_parse_amount(content["amount_minor"]),
                currency=currency,
                description=content["description"],
                category=content.get("category"),
                external_id=content.get("external_id"),
            ),
        )
