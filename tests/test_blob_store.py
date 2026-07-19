"""Tests for the blob store adapters (T6.1)."""

from pathlib import Path

import pytest

from mylife.knowledge.blob_store import (
    BlobNotFoundError,
    FilesystemBlobStore,
    InMemoryBlobStore,
)


def test_filesystem_round_trip(tmp_path: Path) -> None:
    store = FilesystemBlobStore(tmp_path)
    store.put("user-1/doc-1", b"hello")
    assert store.exists("user-1/doc-1")
    assert store.get("user-1/doc-1") == b"hello"
    store.delete("user-1/doc-1")
    assert not store.exists("user-1/doc-1")


def test_filesystem_missing_raises(tmp_path: Path) -> None:
    store = FilesystemBlobStore(tmp_path)
    with pytest.raises(BlobNotFoundError):
        store.get("nope")
    with pytest.raises(BlobNotFoundError):
        store.delete("nope")


def test_filesystem_key_cannot_escape_root(tmp_path: Path) -> None:
    store = FilesystemBlobStore(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        store.put("../evil", b"x")


def test_in_memory_round_trip() -> None:
    store = InMemoryBlobStore()
    store.put("k", b"data")
    assert store.exists("k")
    assert store.get("k") == b"data"
    store.delete("k")
    assert not store.exists("k")
    with pytest.raises(BlobNotFoundError):
        store.get("k")
