"""Tests for same-origin SPA serving (T11.1)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mylife.core.config import get_settings
from mylife.main import create_app


@pytest.fixture
def spa_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>My Life</title>")
    (static / "assets" / "app.js").write_text("console.log('hi')")
    monkeypatch.setenv("MYLIFE_STATIC_DIR", str(static))
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()


def test_serves_index_at_root(spa_client: TestClient) -> None:
    response = spa_client.get("/")
    assert response.status_code == 200
    assert "My Life" in response.text


def test_spa_history_fallback(spa_client: TestClient) -> None:
    # A client-side route resolves to index.html so the SPA can route it.
    response = spa_client.get("/finance")
    assert response.status_code == 200
    assert "My Life" in response.text


def test_serves_static_asset(spa_client: TestClient) -> None:
    response = spa_client.get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log" in response.text


def test_api_route_wins_over_spa(spa_client: TestClient) -> None:
    response = spa_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_no_static_mount_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYLIFE_STATIC_DIR", raising=False)
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        assert client.get("/finance").status_code == 404  # no SPA fallback
        assert client.get("/health").status_code == 200
    get_settings.cache_clear()
