"""Bounded source lookups and resumable, plugin-owned maintenance state."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import time
import uuid
from typing import Any


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class Maintenance:
    def __init__(self, context: Any, state: Any, targets: Any = None) -> None:
        self.context, self.state = context, state
        gateway = getattr(context, "state", None)
        self.store = gateway.scoped("cast-maintenance-v2") if gateway else None
        self.scope = digest(["v3", context.config, targets])
        previous = self.read("run:" + self.scope) or {}
        self.run = previous.get("token") if previous.get("status") != "completed" else None
        self.run = self.run or uuid.uuid4().hex
        self.started = time.monotonic()
        self.started_at = time.time()
        self.current: dict[str, str] = {}
        self.write("run:" + self.scope, {"token": self.run, "status": "running"})

    def read(self, key: str) -> Any:
        return self.store.get(key) if self.store else None

    def write(self, key: str, value: Any, ttl: int = 7 * 86400) -> None:
        if self.store:
            self.store.set(key, value, ttl_seconds=ttl)

    def done_key(self, server: str, media: dict) -> str:
        return "done:" + digest([self.run, server, media.get("id")])

    def progress(self, media_key: str = "", title: str = "", source: str = "") -> None:
        if media_key:
            self.current[media_key] = title
        self.write(
            "progress",
            {
                **self.state.result(),
                "current_media": list(self.current.values()),
                "source": source,
                "elapsed_seconds": round(time.monotonic() - self.started),
                "started_at": self.started_at,
                "status": "running",
                "updated_at": int(time.time()),
            },
        )

    def finish(self, status: str) -> None:
        self.write("run:" + self.scope, {"token": self.run, "status": status})
        self.progress()
        self.write("progress", {**(self.read("progress") or self.state.result()), "status": status})


class SourceRequests:
    """Caches remote data, never server metadata or writes; cancelled calls are not cached."""

    METHODS = {"search_source_identity", "detail", "search_people", "person_detail"}

    def __init__(self, original: Any, maintenance: Maintenance) -> None:
        self.original, self.maintenance = original, maintenance
        self.cache: dict[str, Any] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.slots = {"tmdb": asyncio.Semaphore(2), "douban": asyncio.Semaphore(1)}
        self.gates = {key: asyncio.Lock() for key in self.slots}
        self.next_at = dict.fromkeys(self.slots, 0.0)

    def __getattr__(self, name: str) -> Any:
        method = getattr(self.original, name)
        if name not in self.METHODS:
            return method

        async def invoke(*args: Any, **kwargs: Any) -> Any:
            source = str(
                kwargs.get("source") or (args[0] if name in {"detail", "person_detail"} else "tmdb")
            )
            key = "cache:v3:" + digest([name, args, kwargs])
            async with self.locks.setdefault(key, asyncio.Lock()):
                return await self.cached(key, source, method, args, kwargs)

        return invoke

    async def cached(self, key: str, source: str, method: Any, args: Any, kwargs: Any) -> Any:
        value = self.cache.get(key) or self.maintenance.read(key)
        if value is not None:
            self.maintenance.state.cache_hits += 1
            return copy.deepcopy(value["data"])
        self.maintenance.progress(source=source)
        try:
            result = await self.request(source, method, args, kwargs)
        except Exception as error:
            self.maintenance.state.request_failures += 1
            self.maintenance.state.failures += 1
            self.maintenance.context.logger.warning(
                "人物来源请求失败：%s / %s", source, type(error).__name__
            )
            raise
        record = {"data": result}
        self.cache[key] = record
        useful = self.has_data(result)
        if useful and len(json.dumps(record, default=str).encode()) < 190_000:
            try:
                self.maintenance.write(key, record, 86400 if useful else 1800)
            except Exception as error:
                self.maintenance.context.logger.warning(
                    "人物缓存未持久化：%s", type(error).__name__
                )
        return copy.deepcopy(result)

    @staticmethod
    def has_data(result: Any) -> bool:
        if not isinstance(result, dict):
            return bool(result)
        for field in ("items", "cast", "actors"):
            if field in result:
                return bool(result[field])
        if "biography" in result or "works" in result:
            return any(result.get(key) for key in ("biography", "profile", "poster", "works"))
        return bool(result)

    async def request(self, source: str, method: Any, args: Any, kwargs: Any) -> Any:
        source = source if source in self.slots else "tmdb"
        async with self.slots[source]:
            for attempt in range(3):
                await self.pace(source)
                try:
                    async with asyncio.timeout(60):
                        return await method(*args, **kwargs)
                except Exception as error:
                    response = getattr(error, "response", None)
                    status = getattr(response, "status_code", None)
                    if attempt == 2 or status not in {429, 502, 503, 504}:
                        raise
                    delay = self.retry_delay(response, attempt)
                    self.next_at[source] = max(self.next_at[source], time.monotonic() + delay)
                    self.maintenance.context.logger.warning(
                        "人物来源限流或暂不可用：%s，%s 秒后重试", source, delay
                    )
        raise RuntimeError("source retry exhausted")

    @staticmethod
    def retry_delay(response: Any, attempt: int) -> float:
        try:
            return min(60.0, max(2 ** (attempt + 1), float(response.headers.get("Retry-After", 0))))
        except (TypeError, ValueError):
            return float(2 ** (attempt + 1))

    async def pace(self, source: str) -> None:
        async with self.gates[source]:
            await asyncio.sleep(max(0.0, self.next_at[source] - time.monotonic()))
            self.next_at[source] = time.monotonic() + (1.0 if source == "douban" else 0.25)


async def process_checkpoint(
    plugin: Any, context: Any, state: Any, server: str, media: dict
) -> None:
    maintenance = state.maintenance
    key = maintenance.done_key(server, media)
    if maintenance.read(key):
        state.resumed_media += 1
        return
    title = str(media.get("name") or media.get("id") or "未知作品")
    maintenance.progress(key, title)
    started = time.monotonic()
    previous_failures = state.failures
    operation = "media:" + digest([server, media.get("id")])

    def log_event(status: str, message: str, details: dict) -> None:
        level = context.logger.warning if status in {"partial", "failed"} else context.logger.info
        level(
            json.dumps(
                {
                    "plugin_event": {
                        "operation_id": operation,
                        "status": status,
                        "stage": "started" if status == "running" else "completed",
                        "message": message,
                        "details": details,
                    }
                },
                ensure_ascii=False,
            )
        )

    log_event("running", f"演职员资料：{title}", {})
    try:
        outcome = await plugin._process_media(context, state, server, media) or {}
        status = outcome.get("status", "completed")
        if str(media.get("id")) in state.retry_media or state.failures != previous_failures:
            status = "partial"
        if status == "completed":
            maintenance.write(key, True)
        log_event(
            status,
            f"{title}：{outcome.get('message') or ('处理完成' if status == 'completed' else '存在未完成项目')}",
            {
                **outcome,
                "duration_ms": round((time.monotonic() - started) * 1000),
            },
        )
    except BaseException as error:
        log_event(
            "cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
            f"{title}：处理已中断"
            if isinstance(error, asyncio.CancelledError)
            else f"{title}：处理失败",
            {"error_type": type(error).__name__},
        )
        raise
    finally:
        maintenance.current.pop(key, None)
        maintenance.progress()
