from typing import Any
from .deletion_rules import value

def safe_number(raw):
    return value(raw) or 0


def same_generation(receipt: dict[str, Any], task: dict[str, Any]) -> bool:
    added = safe_number(task.get("added_on"))
    marker = str(receipt.get("ownership_tag") or "")
    tags = {value.strip() for value in str(task.get("tags") or "").split(",")}
    return bool(
        added and safe_number(receipt.get("task_added_on")) == added and marker and marker in tags
    )


