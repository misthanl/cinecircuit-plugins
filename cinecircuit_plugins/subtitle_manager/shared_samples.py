"""Search-local samples shared by the two video fingerprint providers."""
import asyncio
import base64

from .video_hash import sample_ranges


class SharedVideoSamples:
    def __init__(self, media_files):
        self.media_files = media_files
        self._cache = {}
        self._locks = {}

    async def read_samples(self, path, samples):
        lock = self._locks.setdefault(path, asyncio.Lock())
        async with lock:
            if path not in self._cache:
                reader = getattr(self.media_files, "read_samples", None)
                if not callable(reader):
                    raise ValueError("当前主程序不支持视频采样，请更新主程序")
                # Xunlei covers Shooter's head, one-third and tail samples.
                combined = sample_ranges("xunlei") + [sample_ranges("shooter")[1]]
                payload = await reader(path, combined)
                size = payload.get("size", 0)
                rows = payload.get("samples", [])
                if size < 61440 or len(rows) != len(combined):
                    raise ValueError("视频文件过小或采样不完整")
                chunks = []
                for spec, row in zip(combined, rows):
                    start = self._position(size, spec)
                    chunk = base64.b64decode(row["content_base64"], validate=True)
                    if len(chunk) != spec["length"] or row.get("offset", start) != start:
                        raise ValueError("视频采样位置或长度不正确")
                    chunks.append((start, chunk))
                self._cache[path] = (size, chunks)
            size, chunks = self._cache[path]
        result = []
        for spec in samples:
            start, length = self._position(size, spec), spec["length"]
            for offset, chunk in chunks:
                if offset <= start and start + length <= offset + len(chunk):
                    content = chunk[start - offset:start - offset + length]
                    result.append({"offset": start, "content_base64": base64.b64encode(content).decode("ascii")})
                    break
            else:
                raise ValueError("共享视频采样未覆盖请求区间")
        return {"size": size, "samples": result}

    @staticmethod
    def _position(size, spec):
        return size * spec.get("numerator", 0) // spec.get("denominator", 1) + spec.get("offset", 0)
