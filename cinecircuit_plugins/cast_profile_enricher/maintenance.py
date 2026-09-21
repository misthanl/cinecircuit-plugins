"""Bounded source lookups and disposable, plugin-owned maintenance state."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import time
import uuid
from collections import OrderedDict
from typing import Any


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class Maintenance:
    def __init__(self, context: Any, state: Any, targets: Any = None) -> None:
        self.context, self.state = context, state
        gateway = getattr(context, "state", None)
        self.store = gateway.scoped("cast-maintenance-v2") if gateway else None
        self.scope = digest(["v3", context.config, targets])
        self.run = uuid.uuid4().hex
        self.completed: set[str] = set()
        self.cache_ready = False
        self.next_cleanup = 0.0
        self.clean_cache()
        self.started = time.monotonic()
        self.started_at = time.time()
        self.current: dict[str, str] = {}

    def clean_cache(self) -> None:
        if time.monotonic() < self.next_cleanup:
            return
        self.next_cleanup = time.monotonic() + 60
        try:
            prune = getattr(self.store, "prune_cache", None)
            self.cache_ready = bool(
                prune and prune(prefix="cache:", max_entries=1000, max_bytes=8 * 1024 * 1024) < 200
            )
        except Exception:
            self.cache_ready = False

    def read(self, key: str) -> Any:
        try:
            return self.store.get(key) if self.store else None
        except Exception:
            return None

    def write(self, key: str, value: Any, ttl: int = 7 * 86400) -> None:
        if self.store:
            try:
                self.store.set(key, value, ttl_seconds=ttl)
            except Exception:
                pass  # Disposable progress must never interrupt media processing.

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
        self.progress()
        self.write("progress", {**(self.read("progress") or self.state.result()), "status": status})


class SourceRequests:
    """Caches remote data, never server metadata or writes; cancelled calls are not cached."""

    METHODS = {"search_source_identity", "detail", "search_people", "person_detail"}

    def __init__(self, original: Any, maintenance: Maintenance) -> None:
        self.original, self.maintenance = original, maintenance
        self.cache: OrderedDict[str, Any] = OrderedDict()
        self.cache_bytes = 0
        self.locks = [asyncio.Lock() for _ in range(64)]
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
            async with self.locks[int(key[-8:], 16) % len(self.locks)]:
                return await self.cached(key, source, method, args, kwargs)

        return invoke

    async def cached(self, key: str, source: str, method: Any, args: Any, kwargs: Any) -> Any:
        self.maintenance.clean_cache()
        cached = self.cache.get(key)
        value = cached[0] if cached else self.maintenance.read(key)
        if isinstance(value, dict) and "data" in value:
            if cached is None:
                self.remember(key, value["data"], persist=False)
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
        self.remember(key, result)
        return copy.deepcopy(result)

    def remember(self, key: str, result: Any, *, persist: bool = True) -> None:
        record = {"data": result}
        try:
            encoded_size = len(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode()
            )
        except (TypeError, ValueError):
            return
        if encoded_size > 190_000:
            return
        while self.cache and (
            len(self.cache) >= 1000 or self.cache_bytes + encoded_size > 8 * 1024 * 1024
        ):
            _, (_, old_size) = self.cache.popitem(last=False)
            self.cache_bytes -= old_size
        self.cache[key] = (record, encoded_size)
        self.cache_bytes += encoded_size
        if persist and self.has_data(result) and self.maintenance.cache_ready:
            try:
                self.maintenance.store.set_cache(
                    key,
                    record,
                    prefix="cache:",
                    max_entries=1000,
                    max_bytes=8 * 1024 * 1024,
                    ttl_seconds=86400,
                )
            except Exception as error:
                self.maintenance.context.logger.warning(
                    "人物缓存未持久化：%s", type(error).__name__
                )

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


def log_checkpoint_event(
    context: Any, operation: str, status: str, message: str, details: dict
) -> None:
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


async def process_checkpoint(
    plugin: Any, context: Any, state: Any, server: str, media: dict
) -> None:
    maintenance = state.maintenance
    key = maintenance.done_key(server, media)
    if key in maintenance.completed:
        state.resumed_media += 1
        return
    title = str(media.get("name") or media.get("id") or "未知作品")
    maintenance.progress(key, title)
    started = time.monotonic()
    previous_failures = state.failures
    operation = "media:" + digest([server, media.get("id")])

    log_checkpoint_event(context, operation, "running", f"演职员资料：{title}", {})
    try:
        outcome = await plugin._process_media(context, state, server, media) or {}
        status = outcome.get("status", "completed")
        if str(media.get("id")) in state.retry_media or state.failures != previous_failures:
            status = "partial"
        if status == "completed":
            maintenance.completed.add(key)
        log_checkpoint_event(
            context,
            operation,
            status,
            f"{title}：{outcome.get('message') or ('处理完成' if status == 'completed' else '存在未完成项目')}",
            {
                **outcome,
                "duration_ms": round((time.monotonic() - started) * 1000),
            },
        )
    except BaseException as error:
        log_checkpoint_event(
            context,
            operation,
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
