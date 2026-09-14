"""Explicit interval scans and capability-gated event polling."""
import time


async def source_supports_events(storage, source):
    catalog = await storage.configurations()
    return any(row.get("id") == source and row.get("enabled", True) and
               "change_feed" in row.get("capabilities", []) for row in catalog.get("items", []))


async def prepare_triggers(context, state, progress, storage, source, root):
    now = time.time()
    config = context.config
    if context.trigger == "manual":
        state.set("paused", False)
        if not progress["folders"] and not progress["pending"]:
            state.set("rescan_requested", True)
        progress["manual_active"] = True
    events_enabled = bool(config.get("life_events_enabled")) and not config.get("full_scan_enabled")
    if events_enabled:
        events_enabled = await source_supports_events(storage, source)
    marker = float(config.get("life_events_since") or 0)
    if events_enabled and (not progress.get("events_active") or progress.get("events_marker") != marker):
        progress["events_since"] = marker or now
        progress["events_marker"] = marker
    progress["events_active"] = events_enabled
    prepare_interval_scan(config, state, progress, now)
    state.set("progress", progress)


def prepare_interval_scan(config, state, progress, now):
    if config.get("full_scan_enabled"):
        raw = config.get("full_scan_interval_minutes", 60)
        try:
            minutes = float(raw)
            if isinstance(raw, bool) or not minutes.is_integer() or minutes <= 0:
                raise ValueError
            interval = int(minutes) * 60
        except (TypeError, ValueError, OverflowError):
            raise ValueError("请输入大于 0 的整数分钟") from None
        key = f"interval:{int(minutes)}"
        if progress.get("schedule_key") != key:
            progress["next_full_scan"] = now + interval
            progress["schedule_key"] = key
        if now >= progress["next_full_scan"] and not state.get("paused", False):
            state.set("rescan_requested", True)
            progress["next_full_scan"] = now + interval
    else:
        progress.pop("schedule_key", None)
        progress.pop("next_full_scan", None)
