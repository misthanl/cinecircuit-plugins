"""Present source reports without exposing private candidate or captcha payloads."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .online_sources.base import SourceCandidate, SourceError, SourceErrorKind, safe_public_link
from .online_sources.captcha import CaptchaChallenge
from .online_sources.service import SearchReport


class SearchResultPresenter:
    def __init__(
        self,
        *,
        remember_candidate: Callable[[SourceCandidate], str],
        remember_challenge: Callable[[CaptchaChallenge], dict[str, Any]],
        error_dict: Callable[[SourceError], dict[str, Any]],
        fallback_actions: Callable[[], list[dict[str, str]]],
    ) -> None:
        self.remember_candidate = remember_candidate
        self.remember_challenge = remember_challenge
        self.error_dict = error_dict
        self.fallback_actions = fallback_actions

    def present(self, report: SearchReport) -> dict[str, Any]:
        candidates, counts = self._candidates(report)
        challenges = [
            self.remember_challenge(error.challenge)
            for error in report.errors
            if isinstance(error.challenge, CaptchaChallenge)
        ]
        return {
            "sources": [
                {
                    "provider": source.provider,
                    "state": source.state.value,
                    "attempts": source.attempts,
                    "candidate_count": counts.get(source.provider, 0),
                    "raw_candidate_count": len(source.candidates),
                    "errors": [self.error_dict(item) for item in source.errors],
                }
                for source in report.sources
            ],
            "items": candidates,
            "manual_actions": self._manual_actions(report, bool(candidates)),
            "captcha_challenges": challenges,
        }

    def _candidates(self, report: SearchReport) -> tuple[list[dict[str, Any]], dict[str, int]]:
        candidates = []
        counts: dict[str, int] = {}
        for candidate in report.candidates:
            handle = self.remember_candidate(candidate)
            candidates.append({**candidate.as_dict(), "candidate_handle": handle})
            counts[candidate.provider] = counts.get(candidate.provider, 0) + 1
        return candidates, counts

    def _manual_actions(self, report: SearchReport, has_candidates: bool) -> list[dict[str, str]]:
        restricted = any(
            error.kind in {SourceErrorKind.CAPTCHA, SourceErrorKind.LOGIN, SourceErrorKind.QUOTA}
            for error in report.errors
        )
        if has_candidates and not restricted:
            return []
        actions: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for error in report.errors:
            if error.challenge is not None:
                continue
            manual_url = safe_public_link(error.manual_url)
            if manual_url and manual_url not in seen_urls:
                seen_urls.add(manual_url)
                actions.append(
                    {"provider": error.provider, "url": manual_url, "reason": error.message}
                )
        if not has_candidates:
            for action in self.fallback_actions():
                if action["url"] not in seen_urls:
                    seen_urls.add(action["url"])
                    actions.append(action)
        return actions
