"""Use resolved media identity for receipts; treat legacy titles as hints only."""

from typing import Any


def item_key(candidate: dict[str, Any]) -> str:
    values = (candidate.get(key) or "" for key in ("media_type", "source_key", "source_id", "season"))
    return "maoyan:identity:" + ":".join(map(str, values))


def _same_identity(previous: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if not previous.get("source_key") or not previous.get("source_id"):
        return False
    return all(
        str(previous.get(key) or "") == str(candidate.get(key) or "")
        for key in ("media_type", "source_key", "source_id", "season")
    )


def processed(items: Any, candidate: dict[str, Any], title: str) -> bool:
    current = items.get(item_key(candidate))
    if current and current.get("status") == "subscribed":
        return True
    legacy = items.get(f"maoyan:{candidate['media_type']}:{title}")
    if not legacy or legacy.get("status") != "subscribed":
        return False
    payload = legacy.get("payload")
    return isinstance(payload, dict) and _same_identity(payload, candidate)
