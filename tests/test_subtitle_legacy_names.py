import asyncio
import json
from types import SimpleNamespace
from urllib.parse import quote_from_bytes

import httpx
import pytest

from cinecircuit_plugins.subtitle_manager.online_sources.hash_sources import XunleiSource
from cinecircuit_plugins.subtitle_manager.online_sources.legacy_names import legacy_subtitle_name


@pytest.mark.parametrize("encoding", ["utf-8", "gb18030"])
def test_legacy_url_encoded_chinese_basename(encoding):
    name = "简体双语.Inception.2010.ass"
    encoded = quote_from_bytes(("C:\\字幕\\" + name).encode(encoding))
    assert legacy_subtitle_name(encoded) == name


def test_percent_encoded_legacy_suffix_preserves_literal_unicode_and_plus():
    suffix = quote_from_bytes("双语".encode("gb18030"))
    assert legacy_subtitle_name("简体+" + suffix + ".ass") == "简体+双语.ass"


def test_entities_are_decoded_before_removing_remote_directory():
    assert legacy_subtitle_name("C:&#92;下载&#92;chs&amp;eng.srt") == "chs&eng.srt"


def test_mixed_response_records_keep_each_records_encoding():
    async def run():
        names = ["简体双语.ass", "盗梦空间.srt"]
        records = [
            json.dumps({"sname": name}, ensure_ascii=False).encode(encoding)
            for name, encoding in zip(names, ["gb18030", "utf-8"])
        ]
        payload = b'{"sublist":[' + b','.join(records) + b']}'
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=payload))
        async with httpx.AsyncClient(transport=transport) as client:
            source = XunleiSource(client, {}, None)
            rows = await source._rows("abc", None, None)
        request = SimpleNamespace(season=None, episode=None)
        candidates = [
            source._candidate(row, i, request, {"hash": "abc"})
            for i, row in enumerate(rows)
        ]
        assert [row.title for row in candidates] == names
    asyncio.run(run())
