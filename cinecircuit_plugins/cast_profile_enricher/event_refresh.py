from __future__ import annotations

from hashlib import sha256

from app.modules.plugins.contracts import PluginContext, PluginEvent


SOURCE_EVENTS = (
    "metadata.scrape.completed",
    "organizer.completed",
    "sync.completed",
)
REFRESH_EVENT = "cast-profile.media-refresh"


def schedule_refresh(context: PluginContext, event: PluginEvent) -> dict[str, object]:
    """Persist a deduplicated delayed refresh without blocking the event producer."""

    completion_id = str(
        event.data.get("completion_id")
        or event.data.get("operation_id")
        or event.data.get("job_id")
        or event.data.get("event_id")
        or event.data.get("completed_at")
        or ""
    )
    if not completion_id:
        return {"status": "skipped", "reason": "missing_completion_id"}
    completion_key = sha256(
        f"{event.type}:{event.data.get('provider_key', '')}:{completion_id}".encode()
    ).hexdigest()
    delay = max(0, min(3600, int(context.config.get("scrape_delay", 60))))
    payload = {**event.data, "_source_event": event.type}
    scheduled = context.jobs.schedule_event(
        REFRESH_EVENT,
        payload,
        key=f"media:{completion_key}",
        delay_seconds=delay,
    )
    if not scheduled:
        return {"status": "skipped", "reason": "duplicate_media_completion"}
    return {"status": "pending", "delay_seconds": delay}
