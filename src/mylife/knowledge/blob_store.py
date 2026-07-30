"""Blob storage port and a filesystem adapter.

Document **bytes** are raw source data and live in object storage — the
authoritative external system, kept separate from the kernel (raw/normalized/
derived split). ``BlobStore`` is the port; ``FilesystemBlobStore`` is the
local/dev adapter (S3/GCS adapters can follow). See
``specs/domain/knowledge/document-ingest.md`` (T6.1).
"""

from pathlib import Path
from typing import Protocol


class BlobNotFoundError(Exception):
    """Raised when reading or deleting a key that does not exist."""

    def __init__(self, key: str) -> None:
        super().__init__(f"blob {key!r} not found")
        self.key = key


class BlobStore(Protocol):
    """A minimal object-storage port for opaque byte blobs."""

    def put(self, key: str, data: bytes) -> None:
        """Store ``data`` under ``key`` (overwriting)."""
        ...

    def get(self, key: str) -> bytes:
        """Return the bytes at ``key`` or raise :class:`BlobNotFoundError`."""
        ...

    def delete(self, key: str) -> None:
        """Remove ``key``; raise :class:`BlobNotFoundError` if absent."""
        ...

    def exists(self, key: str) -> bool:
        """Return whether ``key`` is present."""
        ...


class FilesystemBlobStore:
    """A ``BlobStore`` backed by a directory tree under ``root``.

    Keys may contain ``/`` (e.g. ``"<user_id>/<document_id>"``); they map to
    nested paths under ``root``. Keys are constrained to stay within ``root``.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if self._root not in path.parents and path != self._root:
            raise ValueError(f"blob key {key!r} escapes the store root")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise BlobNotFoundError(key) from exc

    def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise BlobNotFoundError(key) from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


class InMemoryBlobStore:
    """An in-memory ``BlobStore`` for tests."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self._blobs[key] = data

    def get(self, key: str) -> bytes:
        try:
            return self._blobs[key]
        except KeyError as exc:
            raise BlobNotFoundError(key) from exc

    def delete(self, key: str) -> None:
        try:
            del self._blobs[key]
        except KeyError as exc:
            raise BlobNotFoundError(key) from exc

    def exists(self, key: str) -> bool:
        return key in self._blobs
