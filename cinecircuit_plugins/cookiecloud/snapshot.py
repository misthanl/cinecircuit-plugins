from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any


SNAPSHOT_NAMESPACE = "cookiecloud.snapshot"
SNAPSHOT_MANIFEST_KEY = "manifest"
SNAPSHOT_CHUNK_PREFIX = "chunk."
SNAPSHOT_CHUNK_CHARACTERS = 180_000
MAX_SNAPSHOT_CHARACTERS = 8 * 1024 * 1024


def snapshot_state(state: Any) -> Any:
    return state.scoped(SNAPSHOT_NAMESPACE)


def store_snapshot(state: Any, *, uuid: str, encrypted: str, crypto_type: str) -> dict[str, Any]:
    if not encrypted or len(encrypted) > MAX_SNAPSHOT_CHARACTERS:
        raise ValueError("CookieCloud 快照大小无效")
    scoped = snapshot_state(state)
    chunks = [
        encrypted[index : index + SNAPSHOT_CHUNK_CHARACTERS]
        for index in range(0, len(encrypted), SNAPSHOT_CHUNK_CHARACTERS)
    ]
    previous = scoped.get(SNAPSHOT_MANIFEST_KEY, {})
    previous_count = int(previous.get("chunk_count") or 0) if isinstance(previous, dict) else 0
    for index, chunk in enumerate(chunks):
        scoped.set(f"{SNAPSHOT_CHUNK_PREFIX}{index:04d}", chunk)
    for index in range(len(chunks), previous_count):
        scoped.delete(f"{SNAPSHOT_CHUNK_PREFIX}{index:04d}")
    manifest = {
        "uuid_sha256": hashlib.sha256(uuid.encode()).hexdigest(),
        "crypto_type": str(crypto_type or "legacy"),
        "chunk_count": len(chunks),
        "encrypted_sha256": hashlib.sha256(encrypted.encode()).hexdigest(),
        "uploaded_at": datetime.now(UTC).isoformat(),
    }
    scoped.set(SNAPSHOT_MANIFEST_KEY, manifest)
    return manifest


def load_snapshot(state: Any, *, uuid: str) -> dict[str, Any] | None:
    scoped = snapshot_state(state)
    manifest = scoped.get(SNAPSHOT_MANIFEST_KEY)
    if not isinstance(manifest, dict):
        return None
    if manifest.get("uuid_sha256") != hashlib.sha256(uuid.encode()).hexdigest():
        return None
    count = int(manifest.get("chunk_count") or 0)
    if count <= 0 or count > 64:
        return None
    chunks = [scoped.get(f"{SNAPSHOT_CHUNK_PREFIX}{index:04d}") for index in range(count)]
    if any(not isinstance(chunk, str) for chunk in chunks):
        return None
    encrypted = "".join(chunks)
    if hashlib.sha256(encrypted.encode()).hexdigest() != manifest.get("encrypted_sha256"):
        return None
    return {
        "encrypted": encrypted,
        "crypto_type": str(manifest.get("crypto_type") or "legacy"),
        "uploaded_at": str(manifest.get("uploaded_at") or ""),
    }
