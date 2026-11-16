"""Bounded JSON transport for public channel catalogs."""

import json

from .errors import BoardRequestError, USER_AGENT

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


async def read_page(client, url, **kwargs):
    # Always close streams, including oversized responses and task cancellation.
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    async with client.stream(kwargs.pop("method", "GET"), url, headers=headers, **kwargs) as response:
        if response.status_code != 200:
            raise BoardRequestError(f"HTTP {response.status_code}")
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                raise BoardRequestError("片库响应超过大小限制")
            body.extend(chunk)
        return body.decode("utf-8")


async def read_json(client, url, **kwargs):
    return json.loads(await read_page(client, url, **kwargs))
