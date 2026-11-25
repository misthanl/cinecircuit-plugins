import asyncio
from types import SimpleNamespace

import pytest

from cinecircuit_plugins.media_cover_generator.api import CoverApi
from cinecircuit_plugins.media_cover_generator.generation import ArtworkGenerationRun
from cinecircuit_plugins.media_cover_generator.plugin import LibraryArtworkPlugin


class MediaServers:
    async def configurations(self):
        return {"items": [
            {"id": "feiniu", "type": "feiniu", "enabled": True, "name": "飞牛"},
            {"id": "disabled", "type": "feiniu", "enabled": False, "name": "停用"},
        ]}

    async def libraries(self, server_id):
        assert server_id == "feiniu"
        return {"items": [{"id": "movies", "name": "电影"}]}


def test_feiniu_is_selectable_and_lists_libraries():
    context = SimpleNamespace(media_servers=MediaServers())
    request = SimpleNamespace(query={"servers": '["feiniu"]'})
    result = asyncio.run(CoverApi(LibraryArtworkPlugin())._targets_api(request, context))
    assert result["servers"] == [{"value": "feiniu", "title": "飞牛"}]
    assert result["libraries"][0]["title"] == "飞牛：电影"


@pytest.mark.parametrize("format", ["jpeg", "apng", "webp"])
def test_feiniu_accepts_supported_generation_formats(format):
    context = SimpleNamespace(config={}, media_servers=MediaServers())
    run = ArtworkGenerationRun(LibraryArtworkPlugin(), context)
    run.image_format = format
    asyncio.run(run._validate_servers(["feiniu"]))
    with pytest.raises(ValueError, match="停用|关闭"):
        asyncio.run(run._validate_servers(["disabled"]))


def test_feiniu_rejects_gif_before_rendering():
    context = SimpleNamespace(config={}, media_servers=MediaServers())
    run = ArtworkGenerationRun(LibraryArtworkPlugin(), context)
    run.image_format = "gif"
    with pytest.raises(ValueError, match="GIF"):
        asyncio.run(run._validate_servers(["feiniu"]))
    run.dry_run = True
    asyncio.run(run._validate_servers(["feiniu"]))


def test_feiniu_history_can_be_reapplied():
    uploads = []
    recorded = []
    applied = []

    class Servers(MediaServers):
        async def set_primary_image(self, server_id, item_id, data, *, content_type):
            uploads.append((server_id, item_id, data, content_type))

    class History:
        def read(self, identity):
            assert identity == "history-1"
            return {
                "id": identity, "server_id": "feiniu", "library_id": "movies",
                "suffix": "jpg",
            }, b"cover"

        def applied(self, identity):
            applied.append(identity)

    context = SimpleNamespace(
        media_servers=Servers(), items=SimpleNamespace(record=lambda *a, **k: recorded.append(a)),
    )
    request = SimpleNamespace(payload={"id": "history-1"})
    result = asyncio.run(CoverApi(LibraryArtworkPlugin())._apply_history(request, context, History()))
    assert result == {"applied": True}
    assert uploads == [("feiniu", "movies", b"cover", "image/jpeg")]
    assert applied == ["history-1"] and len(recorded) == 1
