"""Tests for the knowledge (documents) endpoints (T6.1)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.api.deps import get_blob_store
from mylife.db.base import Base, get_session
from mylife.knowledge import InMemoryBlobStore
from mylife.main import create_app

EMAIL = "ada@example.com"
PASSWORD = "s3cretpw"
DATA = b"fake document bytes"


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    blobs = InMemoryBlobStore()

    def override_session() -> Iterator[Session]:
        yield db

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_blob_store] = lambda: blobs
    with TestClient(app) as test_client:
        yield test_client
    db.close()
    engine.dispose()


def _auth(client: TestClient, email: str = EMAIL) -> dict[str, str]:
    client.post("/users", json={"email": email, "display_name": "Ada", "password": PASSWORD})
    token = client.post("/auth/login", data={"username": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _upload(client: TestClient, auth: dict[str, str]) -> str:
    response = client.post(
        "/documents",
        files={"file": ("statement.pdf", DATA, "application/pdf")},
        headers=auth,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["document_id"])


def test_upload_list_and_download(client: TestClient) -> None:
    auth = _auth(client)
    document_id = _upload(client, auth)

    listed = client.get("/documents", headers=auth)
    assert [d["document_id"] for d in listed.json()] == [document_id]

    meta = client.get(f"/documents/{document_id}", headers=auth)
    assert meta.json()["filename"] == "statement.pdf"

    content = client.get(f"/documents/{document_id}/content", headers=auth)
    assert content.status_code == 200
    assert content.content == DATA
    assert content.headers["content-type"].startswith("application/pdf")


def test_foreign_document_is_404(client: TestClient) -> None:
    owner_auth = _auth(client, "owner@example.com")
    document_id = _upload(client, owner_auth)

    intruder_auth = _auth(client, "intruder@example.com")
    assert client.get(f"/documents/{document_id}", headers=intruder_auth).status_code == 404
    assert client.get(f"/documents/{document_id}/content", headers=intruder_auth).status_code == 404


def test_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/documents").status_code == 401
    assert (
        client.post("/documents", files={"file": ("x.txt", b"x", "text/plain")}).status_code == 401
    )
