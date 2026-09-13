import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image
import pytest

from cinecircuit_plugins.cast_profile_enricher import CastProfileEnricherPlugin
from cinecircuit_plugins.cast_profile_enricher.run_state import RunState


@pytest.mark.parametrize("mode", ["RGB", "RGBA"])
def test_webp_avatar_is_uploaded_as_decodable_png(mode):
    source = BytesIO()
    color = (10, 20, 30, 128) if mode == "RGBA" else (10, 20, 30)
    Image.new(mode, (16, 20), color).save(source, "WEBP", lossless=True)
    upload = AsyncMock()
    context = SimpleNamespace(
        media=SimpleNamespace(download_image=AsyncMock(return_value=source.getvalue())),
        media_servers=SimpleNamespace(set_primary_image=upload),
    )
    state = RunState()
    asyncio.run(
        CastProfileEnricherPlugin()._update_profile_image(
            context, state, "server", "person", {"profile": "https://example.org/avatar.webp"}
        )
    )
    assert upload.call_args.kwargs["content_type"] == "image/png"
    with Image.open(BytesIO(upload.call_args.args[2])) as image:
        assert image.format == "PNG"
        assert image.size == (16, 20)
        assert image.getpixel((0, 0)) == color
    assert state.updated_images == 1


def test_invalid_webp_is_not_uploaded_or_counted():
    upload = AsyncMock()
    context = SimpleNamespace(
        media=SimpleNamespace(download_image=AsyncMock(return_value=b"RIFF0000WEBPbroken")),
        media_servers=SimpleNamespace(set_primary_image=upload),
    )
    state = RunState()
    with pytest.raises(OSError):
        asyncio.run(
            CastProfileEnricherPlugin()._update_profile_image(
                context, state, "server", "person", {"profile": "https://example.org/avatar.webp"}
            )
        )
    upload.assert_not_called()
    assert state.updated_images == 0
