"""HTTP tests for the admin console API and shared Finance (T2.6)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.config import get_settings
from mylife.db.base import Base, get_session
from mylife.main import create_app

PASSWORD = "s3cretpw"
ADMIN = "root@example.com"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(get_settings(), "admin_emails", ADMIN)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()

    def override_session() -> Iterator[Session]:
        yield db

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    db.close()
    engine.dispose()


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/users", json={"email": email, "display_name": email.split("@")[0], "password": PASSWORD}
    )
    assert response.status_code == 201
    return str(response.json()["user_id"])


def _login(client: TestClient, email: str) -> dict[str, str]:
    token = client.post("/auth/login", data={"username": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _expense(client: TestClient, auth: dict[str, str], account_id: str, desc: str) -> None:
    response = client.post(
        "/finance/expenses",
        json={
            "account_id": account_id,
            "amount_minor": 1000,
            "currency": "BRL",
            "description": desc,
        },
        headers=auth,
    )
    assert response.status_code == 201


def _descriptions(client: TestClient, auth: dict[str, str]) -> set[str]:
    response = client.get("/finance/transactions", headers=auth)
    assert response.status_code == 200
    return {t["description"] for t in response.json()}


def test_admin_routes_require_admin(client: TestClient) -> None:
    _register(client, ADMIN)
    _register(client, "ann@example.com")
    admin = _login(client, ADMIN)
    member = _login(client, "ann@example.com")

    assert client.get("/admin/users").status_code == 401
    assert client.get("/admin/users", headers=member).status_code == 403
    assert client.post("/admin/groups", json={}, headers=member).status_code == 403

    users = client.get("/admin/users", headers=admin)
    assert users.status_code == 200
    roles = {u["email"]: u["role"] for u in users.json()}
    assert roles == {ADMIN: "admin", "ann@example.com": "member"}
    assert client.get("/auth/me", headers=admin).json()["role"] == "admin"


def test_role_changes_and_last_admin_guard(client: TestClient) -> None:
    admin_id = _register(client, ADMIN)
    ann_id = _register(client, "ann@example.com")
    admin = _login(client, ADMIN)

    assert (
        client.patch(f"/admin/users/{admin_id}/role", json={"role": "member"}, headers=admin)
    ).status_code == 409
    promoted = client.patch(f"/admin/users/{ann_id}/role", json={"role": "admin"}, headers=admin)
    assert promoted.status_code == 200 and promoted.json()["role"] == "admin"
    assert (
        client.patch(f"/admin/users/{ann_id}/role", json={"role": "boss"}, headers=admin)
    ).status_code == 422
    unknown = "11111111-1111-1111-1111-111111111111"
    assert (
        client.patch(f"/admin/users/{unknown}/role", json={"role": "admin"}, headers=admin)
    ).status_code == 404


def test_group_members_share_finance(client: TestClient) -> None:
    _register(client, ADMIN)
    owner_id = _register(client, "owner@example.com")
    member_id = _register(client, "member@example.com")
    admin = _login(client, ADMIN)
    owner = _login(client, "owner@example.com")
    member = _login(client, "member@example.com")

    # Before grouping, the member has a private ledger.
    private = client.post("/accounts", json={"name": "Própria", "currency": "BRL"}, headers=member)
    _expense(client, member, private.json()["account_id"], "privada")
    shared = client.post("/accounts", json={"name": "Casa", "currency": "BRL"}, headers=owner)
    shared_account = shared.json()["account_id"]
    _expense(client, owner, shared_account, "do titular")

    group = client.post(
        "/admin/groups", json={"name": "Família", "owner_user_id": owner_id}, headers=admin
    )
    assert group.status_code == 201
    group_id = group.json()["household_id"]
    added = client.post(
        f"/admin/groups/{group_id}/members", json={"user_id": member_id}, headers=admin
    )
    assert added.status_code == 201
    assert {m["user_id"] for m in added.json()["members"]} == {owner_id, member_id}
    again = client.post(
        f"/admin/groups/{group_id}/members", json={"user_id": member_id}, headers=admin
    )
    assert again.status_code == 409

    # The member now works on the owner's ledger, in both directions (AC6).
    assert _descriptions(client, member) == {"do titular"}
    _expense(client, member, shared_account, "do membro")
    assert _descriptions(client, owner) == {"do titular", "do membro"}
    assert client.get("/groups/me", headers=member).json()["owner_user_id"] == owner_id

    # Only the owner may change the Open Finance key (AC8).
    key = {"api_key": "sk-test"}
    assert (
        client.post("/finance/connectors/openfinance/credentials", json=key, headers=member)
    ).status_code == 403
    assert (
        client.post("/finance/connectors/openfinance/credentials", json=key, headers=owner)
    ).status_code == 204
    status = client.get("/finance/connectors/openfinance/credentials", headers=member)
    assert status.json()["connected"] is True

    # The owner cannot be removed; a plain member can (AC4, AC7).
    assert (
        client.delete(f"/admin/groups/{group_id}/members/{owner_id}", headers=admin)
    ).status_code == 409
    assert (
        client.delete(f"/admin/groups/{group_id}/members/{member_id}", headers=admin)
    ).status_code == 204
    assert _descriptions(client, member) == {"privada"}
    assert client.get("/groups/me", headers=member).json() is None

    assert client.delete(f"/admin/groups/{group_id}", headers=admin).status_code == 204
    assert client.get("/admin/groups", headers=admin).json() == []
    assert client.delete(f"/admin/groups/{group_id}", headers=admin).status_code == 404


def test_rename_and_change_owner(client: TestClient) -> None:
    _register(client, ADMIN)
    owner_id = _register(client, "owner@example.com")
    member_id = _register(client, "member@example.com")
    outsider_id = _register(client, "out@example.com")
    admin = _login(client, ADMIN)

    group_id = client.post(
        "/admin/groups", json={"name": "Casa", "owner_user_id": owner_id}, headers=admin
    ).json()["household_id"]
    client.post(f"/admin/groups/{group_id}/members", json={"user_id": member_id}, headers=admin)

    foreign = client.patch(
        f"/admin/groups/{group_id}", json={"owner_user_id": outsider_id}, headers=admin
    )
    assert foreign.status_code == 409
    updated = client.patch(
        f"/admin/groups/{group_id}",
        json={"name": "Família", "owner_user_id": member_id},
        headers=admin,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Família"
    assert updated.json()["owner_user_id"] == member_id
