from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.clock import utc_now
from app.core.local_automation_wakeup import notify_automation_queue
from app.modules.plugins.contracts import PluginContext, PluginEvent
from app.persistence.job_models import AutomationTask


REFRESH_EVENT = "media-cover.scrape-refresh"


def schedule_refresh(context: PluginContext, event: PluginEvent) -> dict:
    """The built-in plugin owns its delayed requests in the existing durable queue."""
    completion_id = str(event.data.get("completion_id") or "")
    if not completion_id:
        return {"status": "skipped", "reason": "missing_completion_id"}
    completion_key = sha256(
        f"{event.data.get('provider_key', '')}:{completion_id}".encode()
    ).hexdigest()
    dedupe_key = f"{context.plugin_id}:scrape:{completion_key}"
    delay = max(0, min(3600, int(context.config.get("delay", 60))))
    # Use the existing queue's persisted deadline, without changing its API or
    # holding the plugin runner's execution slot while the delay elapses.
    try:
        with context.state.session_factory() as session:
            if (
                session.scalar(
                    select(AutomationTask.id)
                    .where(
                        AutomationTask.dedupe_key == dedupe_key,
                    )
                    .limit(1)
                )
                is not None
            ):
                return {"status": "skipped", "reason": "duplicate_scrape_completion"}
            task = AutomationTask(
                queue="plugin",
                task_type="plugin_event",
                origin="event",
                dedupe_key=dedupe_key,
                payload=json.dumps({"event_type": REFRESH_EVENT, "data": dict(event.data)}),
                available_at=utc_now() + timedelta(seconds=delay),
            )
            session.add(task)
            session.commit()
    except IntegrityError:
        return {"status": "skipped", "reason": "duplicate_scrape_completion"}
    try:
        notify_automation_queue("plugin")
    except Exception:
        context.logger.warning("封面更新任务已保存，等待队列重新扫描")
    return {"status": "pending", "delay_seconds": delay}
