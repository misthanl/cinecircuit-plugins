import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cinecircuit_plugins.torrent_transfer.plugin import TorrentTransferPlugin
from cinecircuit_plugins.iyuu_autoseed.plugin import IyuuAutoSeedPlugin
from cinecircuit_plugins._shared.seeding import check_queue, map_path, queue, complete, key_for

SOURCE = {
    "name": "Generic data",
    "hash": "a" * 40,
    "downloader_id": "source",
    "added_on": 10,
    "progress": 100,
    "amount_left": 0,
    "errored": False,
    "state": "stoppedUP",
    "save_path": "/source/data",
    "tags": "transfer,source-tag",
    "category": "archive",
    "size": 1024**3,
}
RECEIPT = {
    "hash": "a" * 40,
    "downloader_id": "target",
    "task_added_on": 20,
    "ownership_verified": True,
    "status": "queued",
    "kind": "qbittorrent",
}


class Items:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return deepcopy(self.values.get(key))

    def record(self, key, status, **values):
        self.values[key] = {"item_key": key, "status": status, **deepcopy(values)}
        return self.get(key)

    def list(self, limit, *, offset=0, status=None):
        values = [v for v in self.values.values() if not status or v["status"] == status]
        return deepcopy(values[offset : offset + limit])


class State:
    def __init__(self, root=None, prefix=""):
        self.root = root if root is not None else {}
        self.prefix = prefix

    def scoped(self, name):
        return State(self.root, name + ":")

    def get(self, key, default=None):
        return deepcopy(self.root.get(self.prefix + key, default))

    def set(self, key, value):
        self.root[self.prefix + key] = deepcopy(value)

    def set_cache(self, key, value, **kwargs):
        self.set(key, value)
        return True

    def clear(self):
        keys = [k for k in self.root if k.startswith(self.prefix)]
        for k in keys:
            del self.root[k]
        return len(keys)


def fixture():
    sdk = SimpleNamespace(
        inventory=AsyncMock(return_value={"items": [deepcopy(SOURCE)], "total": 1}),
        inspect=AsyncMock(return_value=None),
        export=AsyncMock(return_value={"torrent_ref": "opaque"}),
        submit=AsyncMock(return_value=deepcopy(RECEIPT)),
        operate=AsyncMock(),
    )
    config = {
        "enabled": True,
        "fromdownloader": "source",
        "todownloader": "target",
        "includelabels": "transfer",
        "autostart": True,
        "deletesource": True,
    }
    flags = SimpleNamespace(consume_switch=lambda key: bool(config.pop(key, False)))
    broker = SimpleNamespace(
        require=lambda name, min_version=1: flags if name == "configuration" else sdk
    )
    ctx = SimpleNamespace(
        sdk=broker,
        config=config,
        trigger="manual",
        state=State(),
        items=Items(),
        notifications=SimpleNamespace(send=AsyncMock()),
    )
    return ctx, sdk


@pytest.mark.parametrize(
    "changes,selected",
    [
        ({}, True),
        ({"includelabels": "missing"}, False),
        ({"nolabels": "source-tag"}, False),
        ({"includecategory": "other"}, False),
        ({"nopaths": "/source"}, False),
        ({"includelabels": "transfer,source-tag"}, True),
        ({"nopaths": "/source-other"}, True),
    ],
)
def test_transfer_label_category_and_path_filters(changes, selected):
    ctx, _ = fixture()
    ctx.config.update(changes)
    assert TorrentTransferPlugin().selected(SOURCE, ctx.config) is selected


@pytest.mark.parametrize("allow", [True, False])
def test_transfer_empty_tags_switch(allow):
    assert (
        TorrentTransferPlugin().selected({**SOURCE, "tags": ""}, {"transferemptylabel": allow})
        is allow
    )
    assert not TorrentTransferPlugin().selected(
        {**SOURCE, "tags": "刷流"}, {"transferemptylabel": True}
    )


def test_path_mapping_uses_boundaries_and_most_specific_prefix():
    assert map_path("/data/films/A", "/data\n/data/films", "/target\n/movies") == "/movies/A"
    with pytest.raises(ValueError):
        map_path("/data2/A", "/data", "/target")
    with pytest.raises(ValueError):
        map_path("/data/A", "/data\n/source", "/target")


def test_transfer_paused_add_then_recheck_and_delete_only_after_completed_target():
    ctx, sdk = fixture()
    result = asyncio.run(TorrentTransferPlugin().transfer(ctx, sdk))
    assert result["added"] == 1
    assert [c.args[2] for c in sdk.operate.await_args_list] == ["recheck"]
    sdk.inspect.return_value = {
        **SOURCE,
        "hash": RECEIPT["hash"],
        "downloader_id": "target",
        "added_on": 20,
        "progress": 50,
        "amount_left": 10,
    }
    assert asyncio.run(check_queue(ctx, sdk))["source_removed"] == 0
    sdk.inspect.return_value = {**SOURCE, "downloader_id": "target", "added_on": 20}
    counts = asyncio.run(check_queue(ctx, sdk))
    assert counts["started"] == 1 and counts["source_removed"] == 1
    assert [c.args[2] for c in sdk.operate.await_args_list] == ["recheck", "start", "remove"]
    sdk.operate.assert_awaited_with("source", "a" * 40, "remove", added_on=10)
    asyncio.run(check_queue(ctx, sdk))
    assert sdk.operate.await_count == 3


def test_success_dedup_survives_plugin_object_restart_and_preserves_tags_category():
    ctx, sdk = fixture()
    ctx.config.update(
        remainoldtag=True,
        remainoldcat=True,
        add_torrent_tags="moved",
        frompath="/source",
        topath="/target",
    )
    asyncio.run(TorrentTransferPlugin().transfer(ctx, sdk))
    values = sdk.submit.call_args.kwargs
    assert values["tags"] == ["moved", "source-tag", "transfer"] and values["category"] == "archive"
    assert values["save_path"] == "/target/data"
    asyncio.run(TorrentTransferPlugin().transfer(ctx, sdk))
    assert sdk.submit.await_count == 1


def test_unverified_receipt_is_never_started_or_used_to_remove_source():
    ctx, sdk = fixture()
    sdk.submit.return_value = {**RECEIPT, "ownership_verified": False}
    asyncio.run(TorrentTransferPlugin().transfer(ctx, sdk))
    asyncio.run(check_queue(ctx, sdk))
    assert ctx.items.list(10)[0]["status"] == "attention"
    sdk.operate.assert_not_awaited()


def test_existing_incomplete_target_never_removes_source_even_with_duplicate_option():
    ctx, sdk = fixture()
    ctx.config["deleteduplicate"] = True
    sdk.inspect.return_value = {**SOURCE, "progress": 50, "amount_left": 100}
    assert asyncio.run(TorrentTransferPlugin().transfer(ctx, sdk))["skipped"] == 1
    sdk.submit.assert_not_awaited()
    sdk.operate.assert_not_awaited()


def test_interrupted_recheck_is_persisted_and_retried_after_restart():
    ctx, sdk = fixture()
    sdk.operate.side_effect = TimeoutError("offline")
    asyncio.run(TorrentTransferPlugin().transfer(ctx, sdk))
    assert ctx.items.list(10)[0]["status"] == "submitted"
    sdk.operate.side_effect = None
    assert asyncio.run(check_queue(ctx, sdk))["checked"] == 1
    assert ctx.items.list(10)[0]["status"] == "checking"


def test_iyuu_paused_add_reuses_original_paths_and_does_not_change_media():
    ctx, sdk = fixture()
    ctx.config.update(labelsafterseed="cross", addhosttotag=True, auto_category=True)
    exported = {"torrent_ref": "opaque", "files": [{"name": "file.bin", "size": 10}]}
    sdk.site_torrent = AsyncMock(return_value=exported)
    sdk.inspect = AsyncMock(side_effect=[None, {**SOURCE, "files": exported["files"]}])
    result = {"added": 0, "failed": 0, "skipped": 0}
    asyncio.run(
        IyuuAutoSeedPlugin().seed_one(
            ctx,
            sdk,
            SOURCE,
            "target",
            {"id": "site", "name": "Example"},
            {"info_hash": "b" * 40, "torrent_id": 7},
            result,
        )
    )
    assert result["added"] == 1
    values = sdk.submit.call_args.kwargs
    assert values["save_path"] == "/source/data" and values["reuse_save_path"] is True
    assert values["category"] == "archive" and values["tags"] == ["Example", "cross"]
    assert [c.args[2] for c in sdk.operate.await_args_list] == ["recheck"]


def test_iyuu_refuses_mismatching_files_and_records_retryable_failure():
    ctx, sdk = fixture()
    sdk.site_torrent = AsyncMock(
        return_value={"torrent_ref": "opaque", "files": [{"name": "different", "size": 10}]}
    )
    sdk.inspect = AsyncMock(
        side_effect=[None, {**SOURCE, "files": [{"name": "file.bin", "size": 10}]}]
    )
    outcome = {"added": 0, "failed": 0, "skipped": 0}
    plugin = IyuuAutoSeedPlugin()
    asyncio.run(
        plugin.seed_one(
            ctx,
            sdk,
            SOURCE,
            "target",
            {"id": "site", "name": "Example"},
            {"info_hash": "b" * 40, "torrent_id": 7},
            outcome,
        )
    )
    sdk.submit.assert_not_awaited()
    assert outcome["failed"] == 1
    assert plugin.cached(ctx, key_for("target", "b" * 40))


def test_skip_verification_is_only_effective_for_qbittorrent():
    ctx, sdk = fixture()
    ctx.config["skipverify"] = True
    sdk.submit.return_value = {**RECEIPT, "kind": "transmission"}
    asyncio.run(TorrentTransferPlugin().transfer(ctx, sdk))
    sdk.operate.assert_awaited_once_with("target", "a" * 40, "recheck", added_on=20)


def test_declared_config_covers_all_upstream_settings():
    transfer = {
        "enabled",
        "onlyonce",
        "notification_enabled",
        "cron",
        "fromdownloader",
        "todownloader",
        "fromtorrentpath",
        "frompath",
        "topath",
        "path_mappings",
        "includelabels",
        "nolabels",
        "transferemptylabel",
        "includecategory",
        "nopaths",
        "remainoldcat",
        "remainoldtag",
        "add_torrent_tags",
        "skipverify",
        "autostart",
        "deletesource",
        "deleteduplicate",
    }
    iyuu = {
        "enabled",
        "onlyonce",
        "notification_enabled",
        "cron",
        "token",
        "downloaders",
        "auto_downloader",
        "sites",
        "nolabels",
        "nopaths",
        "size",
        "labelsafterseed",
        "categoryafterseed",
        "addhosttotag",
        "auto_category",
        "reuse_save_path",
        "skipverify",
        "auto_start",
        "clearcache",
    }
    for plugin, fields in ((TorrentTransferPlugin, transfer), (IyuuAutoSeedPlugin, iyuu)):
        assert {f["key"] for f in plugin.manifest.config_schema["fields"]} == fields


def test_iyuu_bad_first_batch_does_not_stop_later_batches():
    ctx, sdk = fixture()
    ctx.config.update(downloaders=["source"], token="test-token")
    candidates = [{**SOURCE, "hash": format(i, "040x")} for i in range(201)]
    sdk.inventory.return_value = {"items": candidates, "total": 201}
    sdk.sites = AsyncMock(return_value={"items": []})
    ctx.sites = SimpleNamespace(supported_catalog=AsyncMock(return_value={"items": []}))
    client = SimpleNamespace(
        initialize=AsyncMock(), sites=[], query=AsyncMock(side_effect=[ValueError("bad JSON"), {}])
    )
    plugin = IyuuAutoSeedPlugin()
    plugin.client_factory = lambda token: client
    result = asyncio.run(plugin.reseed(ctx, sdk))
    assert result["failed"] == 200 and client.query.await_count == 2


def test_iyuu_site_mapping_supports_aliases_selected_sites_and_custom_sites():
    ctx, sdk = fixture()
    ctx.config["sites"] = ["local"]
    sdk.sites = AsyncMock(
        return_value={
            "items": [
                {"id": "local", "name": "Example", "enabled": True, "host": "new.example"},
                {"id": "other", "name": "Other", "enabled": True, "host": "custom.example"},
            ]
        }
    )
    ctx.sites = SimpleNamespace(
        supported_catalog=AsyncMock(
            return_value={"items": [{"site_id": "local", "domains": ["old.example"]}]}
        )
    )
    client = SimpleNamespace(
        sites=[
            {"id": 1, "base_url": "https://old.example/"},
            {"id": 2, "base_url": "https://custom.example/"},
        ]
    )
    result = asyncio.run(IyuuAutoSeedPlugin().site_map(ctx, sdk, client))
    assert list(result) == ["1"]
    ctx.config["sites"] = []
    assert len(asyncio.run(IyuuAutoSeedPlugin().site_map(ctx, sdk, client))) == 2


def test_scheduled_disabled_plugin_never_starts_pending_tasks():
    ctx, sdk = fixture()
    ctx.config["enabled"] = False
    ctx.trigger = "scheduled"
    assert asyncio.run(TorrentTransferPlugin().run(ctx))["status"] == "idle"
    sdk.inspect.assert_not_awaited()
    sdk.operate.assert_not_awaited()
