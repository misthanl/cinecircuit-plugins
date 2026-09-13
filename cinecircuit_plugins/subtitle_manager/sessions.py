"""Installation-scoped, expiring candidate and one-shot captcha sessions."""

from __future__ import annotations

import secrets
import time
from typing import Any

from app.modules.plugins.contracts import PluginContext
from .online_sources.base import SourceCandidate
from .online_sources.captcha import CaptchaChallenge


class SubtitleSessions:
    def __init__(self) -> None:
        self._candidate_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._captcha_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def remember_candidate(
        self, context: PluginContext, media_path: str, candidate: SourceCandidate
    ) -> str:
        token = secrets.token_urlsafe(24)
        value = {
            "media_path": media_path,
            "candidate": self.candidate_payload(candidate),
        }
        state = getattr(context, "state", None)
        if state is not None:
            state.scoped("subtitle-search").set(f"candidate:{token}", value, ttl_seconds=600)
        else:
            self._candidate_cache[token] = (time.monotonic() + 600, value)
        return token

    def load_candidate(
        self, context: PluginContext, token: str, media_path: str
    ) -> SourceCandidate:
        state = getattr(context, "state", None)
        value = None
        if state is not None:
            scoped = state.scoped("subtitle-search")
            key = f"candidate:{token}"
            record = scoped.get_record(key)
            if record is not None:
                value = record.get("value")
        else:
            cached = self._candidate_cache.get(token)
            if cached and cached[0] > time.monotonic():
                value = cached[1]
            elif cached:
                self._candidate_cache.pop(token, None)
        if not isinstance(value, dict) or value.get("media_path") != media_path:
            raise ValueError("字幕候选已过期，请重新搜索")
        payload = value.get("candidate")
        if not isinstance(payload, dict):
            raise ValueError("字幕候选已过期，请重新搜索")
        return SourceCandidate(**payload)

    def remember_captcha(
        self,
        context: PluginContext,
        challenge: CaptchaChallenge | dict[str, Any],
        *,
        extra_context: dict[str, Any] | None = None,
    ) -> str:
        payload = (
            challenge.as_dict() if isinstance(challenge, CaptchaChallenge) else dict(challenge)
        )
        resume = dict(payload.get("context") or {})
        if extra_context:
            resume.update(extra_context)
        payload["context"] = resume
        token = secrets.token_urlsafe(24)
        value = {"challenge": payload}
        state = getattr(context, "state", None)
        if state is not None:
            state.scoped("subtitle-captcha").set(f"challenge:{token}", value, ttl_seconds=600)
        else:
            self._captcha_cache[token] = (time.monotonic() + 600, value)
        return token

    def load_captcha(self, context: PluginContext, token: str) -> dict[str, Any]:
        state = getattr(context, "state", None)
        value = None
        if state is not None:
            scoped = state.scoped("subtitle-captcha")
            key = f"challenge:{token}"
            record = scoped.get_record(key)
            if record is not None:
                try:
                    claimed = scoped.delete(key, expected_version=int(record.get("version") or 0))
                except RuntimeError:
                    claimed = False
                if claimed:
                    value = record.get("value")
        else:
            cached = self._captcha_cache.pop(token, None)
            if cached and cached[0] > time.monotonic():
                value = cached[1]
        if not isinstance(value, dict) or not isinstance(value.get("challenge"), dict):
            raise ValueError("验证码会话已过期，请重新搜索")
        return value["challenge"]

    @staticmethod
    def captcha_public(handle: str, challenge: CaptchaChallenge | dict[str, Any]) -> dict[str, Any]:
        payload = (
            challenge.public_dict()
            if isinstance(challenge, CaptchaChallenge)
            else {
                key: challenge.get(key, "") for key in ("provider", "site", "image", "instruction")
            }
        )
        return {"handle": handle, **payload}

    @staticmethod
    def candidate_payload(candidate: SourceCandidate) -> dict[str, Any]:
        metadata = {}
        for key in ("file_match", "identity_match"):
            value = candidate.metadata.get(key)
            if isinstance(value, dict):
                metadata[key] = dict(value)
        return {
            "provider": candidate.provider,
            "result_id": candidate.result_id,
            "title": candidate.title,
            "detail_url": candidate.detail_url,
            "year": candidate.year,
            "season": candidate.season,
            "episode": candidate.episode,
            "language": candidate.language,
            "subtitle_format": candidate.subtitle_format,
            "downloadable": candidate.downloadable,
            "download_ref": candidate.download_ref,
            "score": candidate.score,
            "match_reason": candidate.match_reason,
            "matched": candidate.matched,
            "tags": candidate.tags,
            "metadata": metadata,
        }
