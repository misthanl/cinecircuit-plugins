"""Concurrent orchestration for all online subtitle entry points."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .base import (
    DownloadResult,
    OnlineSource,
    SearchRequest,
    SourceCandidate,
    SourceError,
    SourceErrorKind,
    SourceFailure,
    SourceSearchResult,
    SourceState,
    enrich_candidate,
)
from .matcher import merge_and_rank


@dataclass(frozen=True, slots=True)
class SearchReport:
    candidates: tuple[SourceCandidate, ...]
    sources: tuple[SourceSearchResult, ...]

    @property
    def errors(self) -> tuple[SourceError, ...]:
        return tuple(error for source in self.sources for error in source.errors)


class OnlineSubtitleService:
    """One service shared by page previews and automatic event execution."""

    def __init__(
        self,
        sources: Iterable[OnlineSource],
        *,
        timeout: float = 12.0,
        retries: int = 1,
    ):
        self.sources = tuple(sources)
        self.timeout = max(0.01, timeout)
        self.retries = max(0, retries)

    async def search(self, requests: SearchRequest | Sequence[SearchRequest]) -> SearchReport:
        plans = (requests,) if isinstance(requests, SearchRequest) else tuple(requests)
        source_results = await asyncio.gather(
            *(self._bounded_source_search(source, plans) for source in self.sources)
        )
        pairs = [
            (candidate, request)
            for source_result, tagged in source_results
            for candidate, request in tagged
        ]
        return SearchReport(merge_and_rank(pairs), tuple(item[0] for item in source_results))

    async def search_sequential(
        self, requests: SearchRequest | Sequence[SearchRequest]
    ) -> AsyncIterator[SearchReport]:
        """Search the next configured source only when the caller requests it."""
        plans = (requests,) if isinstance(requests, SearchRequest) else tuple(requests)
        for source in self.sources:
            result, tagged = await self._bounded_source_search(source, plans)
            yield SearchReport(merge_and_rank(tagged), (result,))

    async def _bounded_source_search(
        self, source: OnlineSource, requests: tuple[SearchRequest, ...]
    ) -> tuple[SourceSearchResult, list[tuple[SourceCandidate, SearchRequest]]]:
        # Keep the complete alias plan below the host's 30-second page API budget.
        budget = min(24.0, self.timeout * (self.retries + 1))
        return await self._search_source(source, requests, budget=budget)

    async def _search_source(
        self,
        source: OnlineSource,
        requests: tuple[SearchRequest, ...],
        *,
        budget: float | None = None,
    ) -> tuple[SourceSearchResult, list[tuple[SourceCandidate, SearchRequest]]]:
        candidates: list[SourceCandidate] = []
        tagged: list[tuple[SourceCandidate, SearchRequest]] = []
        errors: list[SourceError] = []
        attempts = 0
        deadline = asyncio.get_running_loop().time() + (budget or float("inf"))

        def remaining_timeout() -> float:
            return min(self.timeout, max(0.0, deadline - asyncio.get_running_loop().time()))

        state, status_error = await self._source_status(source, remaining_timeout())
        if status_error is not None:
            return SourceSearchResult(
                source.name, SourceState.ERROR, errors=(status_error,), attempts=0
            ), tagged
        if state is SourceState.DISABLED:
            error = SourceError(
                source.name,
                SourceErrorKind.CONFIGURATION,
                f"{source.name} 未启用或配置不完整",
            )
            return SourceSearchResult(source.name, state, errors=(error,), attempts=0), tagged
        for request in requests:
            if remaining_timeout() <= 0:
                errors.append(self._timeout_error(source, total=True))
                break
            result, request_errors, used_attempts = await self._search_request(
                source, request, remaining_timeout
            )
            attempts += used_attempts
            errors.extend(request_errors)
            if result is None:
                continue
            state = result.state
            errors.extend(result.errors)
            enriched = tuple(enrich_candidate(candidate) for candidate in result.candidates)
            candidates.extend(enriched)
            tagged.extend((candidate, request) for candidate in enriched)
        state = self._search_result_state(state, errors, candidates)
        return SourceSearchResult(
            source.name, state, tuple(candidates), tuple(errors), attempts
        ), tagged

    @staticmethod
    def _search_result_state(
        state: SourceState, errors: list[SourceError], candidates: list[SourceCandidate]
    ) -> SourceState:
        if any(
            error.kind in {SourceErrorKind.CAPTCHA, SourceErrorKind.LOGIN, SourceErrorKind.QUOTA}
            for error in errors
        ):
            state = SourceState.RESTRICTED
        elif errors and not candidates:
            state = SourceState.ERROR
        return state

    async def _source_status(
        self, source: OnlineSource, timeout: float
    ) -> tuple[SourceState, SourceError | None]:
        try:
            return await asyncio.wait_for(source.status(), timeout=timeout), None
        except TimeoutError:
            return SourceState.ERROR, SourceError(
                source.name,
                SourceErrorKind.TIMEOUT,
                f"{source.name} 状态检查超时",
                True,
            )
        except Exception:
            return SourceState.ERROR, SourceError(
                source.name,
                SourceErrorKind.NETWORK,
                f"{source.name} 状态检查失败",
                True,
            )

    async def _search_request(
        self,
        source: OnlineSource,
        request: SearchRequest,
        remaining_timeout: Callable[[], float],
    ) -> tuple[SourceSearchResult | None, tuple[SourceError, ...], int]:
        attempts = 0
        for attempt in range(self.retries + 1):
            timeout = remaining_timeout()
            if timeout <= 0:
                return None, (self._timeout_error(source, total=True),), attempts
            attempts += 1
            try:
                result = await asyncio.wait_for(source.search(request), timeout=timeout)
            except TimeoutError:
                error = self._timeout_error(source)
            except SourceFailure as exc:
                error = exc.error
            except Exception:
                error = SourceError(
                    source.name,
                    SourceErrorKind.NETWORK,
                    f"{source.name} 搜索失败",
                    True,
                )
            else:
                retry = (
                    not result.candidates
                    and any(error.retryable for error in result.errors)
                    and attempt < self.retries
                )
                if retry:
                    continue
                return result, (), attempts
            if not error.retryable or attempt >= self.retries:
                return None, (error,), attempts
        return None, (), attempts

    @staticmethod
    def _timeout_error(source: OnlineSource, *, total: bool = False) -> SourceError:
        label = "搜索总时限已到" if total else "搜索超时"
        return SourceError(
            source.name,
            SourceErrorKind.TIMEOUT,
            f"{source.name} {label}",
            True,
        )

    async def download(
        self, candidate: SourceCandidate, *, require_match: bool = True
    ) -> DownloadResult:
        if require_match and not candidate.matched:
            return DownloadResult(
                candidate.provider,
                error=SourceError(
                    candidate.provider,
                    SourceErrorKind.DOWNLOAD,
                    "候选尚未通过媒体身份校验",
                ),
            )
        source = next((item for item in self.sources if item.name == candidate.provider), None)
        if source is None:
            return DownloadResult(
                candidate.provider,
                error=SourceError(
                    candidate.provider, SourceErrorKind.CONFIGURATION, "字幕来源未启用"
                ),
            )
        try:
            return await asyncio.wait_for(source.download(candidate), timeout=self.timeout)
        except TimeoutError:
            return DownloadResult(
                candidate.provider,
                error=SourceError(
                    candidate.provider,
                    SourceErrorKind.TIMEOUT,
                    f"{candidate.provider} 下载超时",
                    True,
                    candidate.detail_url,
                ),
            )
        except SourceFailure as exc:
            return DownloadResult(candidate.provider, error=exc.error)
        except Exception:
            return DownloadResult(
                candidate.provider,
                error=SourceError(
                    candidate.provider,
                    SourceErrorKind.DOWNLOAD,
                    f"{candidate.provider} 下载失败",
                    True,
                    candidate.detail_url,
                ),
            )

    @staticmethod
    def request_from_plan(
        plan: Any, identity: Any | None = None, *, language: str = ""
    ) -> SearchRequest:
        """Compatibility adapter for external callers that still pass plan objects."""
        if isinstance(plan, SearchRequest):
            return plan
        query = str(
            getattr(plan, "query", None)
            or getattr(plan, "keyword", None)
            or (plan.get("query") if isinstance(plan, dict) else "")
            or (plan.get("keyword") if isinstance(plan, dict) else "")
        )
        source_identity = (
            identity
            or getattr(plan, "identity", None)
            or (plan.get("identity") if isinstance(plan, dict) else None)
        )
        return SearchRequest.from_identity(source_identity, query, language=language)
