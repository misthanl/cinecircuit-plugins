"""Two-item identity lookahead with ordered consumption and cancellation cleanup."""

import asyncio
from collections import deque
from contextlib import asynccontextmanager
from typing import Any
from .timing import stage_timing


@asynccontextmanager
async def identity_prefetch(context: Any, rows: list[dict], resolver: Any, cache: dict):
    pending: deque[tuple[dict, asyncio.Task]] = deque()
    iterator = iter(row for row in rows if row.get("title"))

    async def resolve(row):
        with stage_timing(context, "prepare", str(row["title"])):
            return await resolver(context, row, cache)

    def fill():
        while len(pending) < 2:
            row = next(iterator, None)
            if row is None:
                break
            pending.append((row, asyncio.create_task(resolve(row))))

    async def ordered():
        fill()
        while pending:
            row, task = pending[0]
            yield row, task
            pending.popleft()
            fill()

    try:
        yield ordered()
    finally:
        for _, task in pending:
            task.cancel()
        await asyncio.gather(*(task for _, task in pending), return_exceptions=True)
        pending.clear()
        cache.clear()
