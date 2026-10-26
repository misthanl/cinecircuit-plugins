import asyncio
from hashlib import sha1
import json
from unittest.mock import AsyncMock
import pytest
from cinecircuit_plugins.iyuu_autoseed.client import IyuuClient


def test_query_uses_upstream_signature_and_refreshes_stale_site_digest():
    client = IyuuClient("token")
    client.sites = [{"id": 1}]
    client.sid_sha1 = "old"
    client.request = AsyncMock(
        side_effect=[ValueError("站点哈希值 require"), {"sid_sha1": "new"}, {"result": True}]
    )
    assert asyncio.run(client.query(["b", "a"])) == {"result": True}
    values = client.request.await_args_list
    payload = values[0].args[1]
    assert payload["hash"] == '["a","b"]' and payload["sha1"] == sha1(b'["a","b"]').hexdigest()
    assert values[-1].args[1]["sid_sha1"] == "new"


def test_invalid_json_is_bounded_and_does_not_leak_token(monkeypatch):
    import httpx
    from cinecircuit_plugins.iyuu_autoseed import client as module

    def factory(**options):
        return httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text="<html>invalid</html>")
            )
        )

    monkeypatch.setattr(module, "http_client", factory)
    with pytest.raises(ValueError, match="JSON") as error:
        asyncio.run(IyuuClient("private-token").request("/test"))
    assert "private-token" not in str(error.value)
