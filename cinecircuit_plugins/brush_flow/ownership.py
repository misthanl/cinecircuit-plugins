from typing import Any
from .deletion_rules import value


def safe_number(raw):
    return value(raw) or 0


def same_generation(receipt: dict[str, Any], task: dict[str, Any]) -> bool:
    added = safe_number(task.get("added_on"))
    return bool(
        receipt.get("ownership_verified")
        and added
        and safe_number(receipt.get("task_added_on")) == added
        and str(receipt.get("hash") or "").casefold() == str(task.get("hash") or "").casefold()
        and str(receipt.get("downloader_id") or "") == str(task.get("downloader_id") or "")
    )
