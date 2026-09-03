import asyncio
from datetime import datetime, timedelta
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.application_events import publish_metadata_scraped
from app.db.model_registry import Base
from app.modules.automation import task_queue as automation_queue_module
from app.modules.automation.task_queue import AutomationTaskQueue
from app.modules.config.service import ConfigService
from app.modules.organizer.manual_task_queue import ManualMediaTaskQueue
from app.modules.pipeline import scrape_queue as scrape_queue_module
from cinecircuit_plugins.media_cover_generator import LibraryArtworkPlugin
from cinecircuit_plugins.media_cover_generator import plugin as cover_plugin_module
from cinecircuit_plugins.media_cover_generator import scrape_refresh
from app.modules.plugins.contracts import PluginEvent
from app.modules.plugins.runner import PluginRunner
from app.modules.plugins.service import PluginService
from app.persistence.job_models import AutomationTask
from app.persistence.organizer_models import ManualMediaTask
from app.workers.automation_worker import _automation_executors


@pytest.fixture
def services(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'scrape-cover.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    config = ConfigService(factory)
    plugins = PluginService(factory)
    plugins.install(
        LibraryArtworkPlugin.manifest,
        owner_user_id=1,
        source="builtin",
        trusted=True,
    )
    plugins.update(
        "emby-cover-generator",
        enabled=True,
        config={"enabled": False, "transfer_monitor": True, "delay": 60, "dry_run": True},
    )
    monkeypatch.setattr(automation_queue_module, "_notify_committed_queue", lambda _: None)
    monkeypatch.setattr(scrape_refresh, "notify_automation_queue", lambda _: None)
    return config, plugins, factory


def tasks(factory):
    with factory() as session:
        return list(session.scalars(select(AutomationTask)))


def publish(config, *, generated_files=3):
    publish_metadata_scraped(
        config,
        completion_id="batch:one",
        provider_key="115",
        generated_files=generated_files,
    )


def deliver_next(config, plugins, queue):
    task = queue.claim_next("plugin")
    assert task is not None
    runner = PluginRunner(config, plugins)

    class Runtime:
        async def publish_plugin_event(self, event_type, data):
            await runner._handle_event(PluginEvent(event_type, data))

    result = asyncio.run(
        _automation_executors(Runtime())["plugin_event"](json.loads(task.payload), task)
    )
    assert queue.complete(task.id, result)


def refresh_tasks(factory):
    return [
        row
        for row in tasks(factory)
        if json.loads(row.payload)["event_type"] == scrape_refresh.REFRESH_EVENT
    ]


def test_delayed_completion_survives_queue_recreation_and_runs_once(services, monkeypatch):
    config, plugins, factory = services
    now = datetime(2030, 9, 3, 12)
    monkeypatch.setattr(scrape_refresh, "utc_now", lambda: now)
    monkeypatch.setattr(automation_queue_module, "utc_now", lambda: now)
    publish(config)
    publish(config)
    assert len(tasks(factory)) == 2  # The host publishes both completion events.
    queue = AutomationTaskQueue(factory)
    deliver_next(config, plugins, queue)
    deliver_next(config, plugins, queue)
    (row,) = refresh_tasks(factory)  # Only the plugin deduplicates cover requests.
    assert row.available_at == now + timedelta(seconds=60)
    assert row.origin == "event"
    assert AutomationTaskQueue(factory).claim_next("plugin") is None

    # A new worker uses the persisted deadline; it does not sleep in the scrape worker.
    now += timedelta(seconds=60)
    queue = AutomationTaskQueue(factory)
    generated = []

    async def generate(run):
        generated.append((run.context.trigger, run.dry_run))
        return {"preview_count": 1, "updated_count": 0}

    monkeypatch.setattr(cover_plugin_module.ArtworkGenerationRun, "run", generate)
    deliver_next(config, plugins, queue)
    assert generated == [("event", True)]
    publish(config)
    deliver_next(config, plugins, queue)
    assert len(refresh_tasks(factory)) == 1
    assert queue.claim_next("plugin") is None
    runs = plugins.list_runs("emby-cover-generator")
    generated_runs = [run for run in runs if run["result"].get("preview_count")]
    assert len(generated_runs) == 1
    assert generated_runs[0]["trigger"] == "event"


@pytest.mark.parametrize("mode", ["uninstalled", "disabled", "monitor_off", "unchanged"])
def test_host_always_publishes_but_plugin_can_skip_update(services, mode):
    config, plugins, factory = services
    if mode == "uninstalled":
        plugins.update("emby-cover-generator", enabled=False)
        plugins.uninstall("emby-cover-generator")
    elif mode == "disabled":
        plugins.update("emby-cover-generator", enabled=False)
    elif mode == "monitor_off":
        plugins.update("emby-cover-generator", config={"transfer_monitor": False})
    publish(config, generated_files=0 if mode == "unchanged" else 3)
    (event,) = tasks(factory)
    assert json.loads(event.payload)["event_type"] == "metadata.scrape.completed"
    deliver_next(config, plugins, AutomationTaskQueue(factory))
    assert refresh_tasks(factory) == []


@pytest.mark.parametrize("disable_plugin", [False, True])
def test_switch_or_plugin_disabled_during_delay_prevents_generation(
    services,
    monkeypatch,
    disable_plugin,
):
    config, plugins, factory = services
    publish(config)
    deliver_next(config, plugins, AutomationTaskQueue(factory))
    assert len(refresh_tasks(factory)) == 1
    if disable_plugin:
        plugins.update("emby-cover-generator", enabled=False)
    else:
        plugins.update("emby-cover-generator", config={"transfer_monitor": False})

    async def unexpected_generation(_run):
        pytest.fail("disabled cover generation must not run")

    monkeypatch.setattr(cover_plugin_module.ArtworkGenerationRun, "run", unexpected_generation)
    payload = json.loads(refresh_tasks(factory)[0].payload)
    runner = PluginRunner(config, plugins)
    asyncio.run(runner._handle_event(PluginEvent(payload["event_type"], payload["data"])))
    runs = plugins.list_runs("emby-cover-generator")
    if disable_plugin:
        assert len(runs) == 1  # Only the initial scheduling event was handled.
    else:
        assert runs[0]["result"]["reason"] == "scrape_monitor_disabled"


def test_batch_completion_enqueues_once_even_when_notification_retries(services, monkeypatch):
    config, plugins, factory = services
    summary = {
        "batch_id": "one",
        "total": 2,
        "completed": 1,
        "generated_files": 3,
        "unchanged": 0,
        "partial": 0,
        "failed": 1,
        "discarded": 0,
    }
    marked = []
    queue = SimpleNamespace(
        config_service=config,
        provider_key="115",
        claim_completed_batch_notifications=lambda: [summary],
        mark_batch_notified=marked.append,
    )

    async def unconfirmed(*_args):
        return False

    monkeypatch.setattr(scrape_queue_module, "_deliver_scrape_batch_notification", unconfirmed)
    asyncio.run(scrape_queue_module._notify_completed_scrape_batches(queue))
    asyncio.run(scrape_queue_module._notify_completed_scrape_batches(queue))
    assert marked == []
    assert len(tasks(factory)) == 2
    payload = json.loads(tasks(factory)[0].payload)
    assert payload["data"]["completion_id"] == "batch:one"
    delivery_queue = AutomationTaskQueue(factory)
    deliver_next(config, plugins, delivery_queue)
    deliver_next(config, plugins, delivery_queue)
    assert len(refresh_tasks(factory)) == 1


@pytest.mark.parametrize(
    "task_type,outputs,expected",
    [
        ("manual_scrape", 2, 1),
        ("manual_scrape", 0, 1),
        ("manual_organize_source", 2, 0),
    ],
)
def test_manual_task_only_emits_after_scraping(services, monkeypatch, task_type, outputs, expected):
    config, _plugins, factory = services
    queue = ManualMediaTaskQueue(config, factory)
    with factory() as session:
        task = ManualMediaTask(
            task_type=task_type,
            provider_key="local",
            status="processing",
            extension_version="1",
            capability_snapshot='{"local_organizer":true}',
        )
        session.add(task)
        session.commit()

    async def execute(_task):
        assert tasks(factory) == []
        return {"scraped": 1 if outputs else 0, "outputs": outputs, "failed": 0}

    monkeypatch.setattr(queue, "_execute", execute)
    assert asyncio.run(queue._process_manual_task(task))
    assert len(tasks(factory)) == expected
    with factory() as session:
        assert session.get(ManualMediaTask, task.id).status == "completed"
