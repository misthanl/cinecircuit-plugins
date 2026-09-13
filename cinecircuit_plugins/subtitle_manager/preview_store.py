"""Short-lived disk previews awaiting explicit user confirmation."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.modules.plugins.runtime_services import data_directory

MAX_PREVIEW_FILES = 64


@dataclass(frozen=True)
class PreviewFile:
    extension: str
    language: str
    content: bytes
    source_name: str
    details: dict[str, Any]

    def public(self, index: int) -> dict[str, Any]:
        text = self.content.decode("utf-8", errors="replace")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        safe_details: dict[str, Any] = {
            key: self.details[key]
            for key in ("provider", "bilingual", "converted")
            if key in self.details
        }
        return {
            **safe_details,
            "index": index,
            "name": self.source_name,
            "language": self.language,
            "format": self.extension.upper(),
            "bytes": len(self.content),
            "excerpt": "\n".join(lines[:12])[:1200],
        }


class SubtitlePreviewStore:
    """Persist only validated subtitle bytes under a bounded plugin data spool."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        ttl_seconds: int = 10 * 60,
        max_entries: int = 24,
        max_total_bytes: int = 32 * 1024 * 1024,
    ) -> None:
        self.root = root or data_directory("subtitle-manager") / "previews"
        self.ttl_seconds = max(30, int(ttl_seconds))
        self.max_entries = max(1, int(max_entries))
        self.max_total_bytes = max(1024, int(max_total_bytes))

    def create(self, media_path: str, files: list[PreviewFile]) -> dict[str, Any]:
        if not media_path or not files:
            raise ValueError("没有可预览的字幕文件")
        if len(files) > MAX_PREVIEW_FILES:
            raise ValueError("字幕预览文件数量超过限制")
        total = sum(len(item.content) for item in files)
        if total > self.max_total_bytes:
            raise ValueError("字幕预览内容超过大小限制")
        self.root.mkdir(parents=True, exist_ok=True)
        self._prune(required_bytes=total, required_entries=1)
        token = secrets.token_urlsafe(24)
        temporary = self.root / f".{token}.{os.getpid()}.tmp"
        target = self.root / token
        temporary.mkdir(mode=0o700)
        try:
            metadata: dict[str, Any] = {
                "media_path": media_path,
                "created_at": time.time(),
                "expires_at": time.time() + self.ttl_seconds,
                "files": [],
            }
            for index, item in enumerate(files):
                filename = f"{index}.bin"
                (temporary / filename).write_bytes(item.content)
                metadata["files"].append(
                    {
                        "file": filename,
                        "extension": item.extension,
                        "language": item.language,
                        "source_name": item.source_name,
                        "details": item.details,
                    }
                )
            (temporary / "preview.json").write_text(
                json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
            )
            temporary.replace(target)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return {
            "preview_token": token,
            "expires_in": self.ttl_seconds,
            "items": [item.public(index) for index, item in enumerate(files)],
        }

    def consume(
        self, token: str, media_path: str, selected: list[int] | None = None
    ) -> tuple[PreviewFile, ...]:
        self._prune()
        directory = self._token_directory(token)
        claimed = self.root / f".claim-{token}-{secrets.token_urlsafe(6)}"
        try:
            try:
                directory.replace(claimed)
            except FileNotFoundError as error:
                raise ValueError("字幕预览已被使用或已过期") from error
            metadata = json.loads((claimed / "preview.json").read_text(encoding="utf-8"))
            if metadata.get("media_path") != media_path:
                raise ValueError("字幕预览与当前媒体不匹配")
            rows = metadata.get("files") if isinstance(metadata.get("files"), list) else []
            indexes = selected if selected is not None else list(range(len(rows)))
            if not indexes or any(
                not isinstance(index, int) or index < 0 or index >= len(rows) for index in indexes
            ):
                raise ValueError("请选择有效的字幕预览项")
            files = []
            for index in dict.fromkeys(indexes):
                row = rows[index]
                files.append(
                    PreviewFile(
                        extension=str(row["extension"]),
                        language=str(row["language"]),
                        content=(claimed / str(row["file"])).read_bytes(),
                        source_name=str(row["source_name"]),
                        details=dict(row.get("details") or {}),
                    )
                )
            return tuple(files)
        except FileNotFoundError as error:
            raise ValueError("字幕预览已过期，请重新下载") from error
        finally:
            shutil.rmtree(claimed, ignore_errors=True)

    def _token_directory(self, token: str) -> Path:
        value = str(token or "")
        if not value or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for character in value
        ):
            raise ValueError("字幕预览令牌无效")
        directory = (self.root / value).resolve()
        if directory.parent != self.root.resolve() or not directory.is_dir():
            raise ValueError("字幕预览已过期，请重新下载")
        return directory

    def _prune(self, *, required_bytes: int = 0, required_entries: int = 0) -> None:
        if not self.root.is_dir():
            return
        now = time.time()
        entries: list[tuple[float, int, Path]] = []
        for directory in self.root.iterdir():
            entry = self._preview_entry(directory, now)
            if entry is not None:
                entries.append(entry)
        total = sum(item[1] for item in entries)
        entries.sort()
        while entries and (
            len(entries) + required_entries > self.max_entries
            or total + required_bytes > self.max_total_bytes
        ):
            _, size, directory = entries.pop(0)
            shutil.rmtree(directory, ignore_errors=True)
            total -= size

    def _preview_entry(self, directory: Path, now: float) -> tuple[float, int, Path] | None:
        if not directory.is_dir() or directory.is_symlink():
            return None
        if directory.name.startswith("."):
            self._prune_temporary(directory, now)
            return None
        try:
            metadata = json.loads((directory / "preview.json").read_text(encoding="utf-8"))
            expires_at = float(metadata.get("expires_at") or 0)
            size = sum(file.stat().st_size for file in directory.iterdir() if file.is_file())
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            expires_at, size, metadata = 0, 0, {}
        if expires_at <= now:
            shutil.rmtree(directory, ignore_errors=True)
            return None
        return float(metadata.get("created_at") or 0), size, directory

    def _prune_temporary(self, directory: Path, now: float) -> None:
        try:
            if now - directory.stat().st_mtime > self.ttl_seconds:
                shutil.rmtree(directory, ignore_errors=True)
        except OSError:
            pass
