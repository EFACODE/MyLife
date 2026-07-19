"""Shared pytest fixtures."""

import pytest
from fastapi.testclient import TestClient

from mylife.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Return a FastAPI test client backed by a fresh application instance."""
    return TestClient(create_app())
