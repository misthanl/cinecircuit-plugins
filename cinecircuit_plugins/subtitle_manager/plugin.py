from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from collections.abc import Callable
from urllib.parse import quote_plus, unquote

from app.modules.plugins.contracts import (
    PluginApiRequest,
    PluginBase,
    PluginContext,
    PluginEvent,
)
from app.modules.plugins.runtime_services import http_client

from .automatic_download import save_candidates
from .event_search import catalog_identity, event_identities
from .identity import (
    MediaIdentity,
    identity_with_warning,
    media_path_key,
    supplement_identity,
)
from .online_sources import (
    AssrtSource,
    ShooterSource,
    XunleiSource,
    SubDLSource,
    CaptchaChallenge,
    OnlineSubtitleService,
    OpenSubtitlesSource,
    SearchRequest,
    SourceCandidate,
    SubHDSource,
    ZimukuSource,
)
from .online_sources.base import OnlineSource, safe_public_link
from .online_sources.captcha import (
    cookies_from_snapshot,
    cookie_snapshot,
    encode_captcha_code,
)
from .preview_store import SubtitlePreviewStore
from .preview_preparation import prepare_previews
from .search_plan import SearchQuery, build_search_plan
from .statistics import summarize
from .manifest import MANIFEST
from .search_results import SearchResultPresenter
from .sessions import SubtitleSessions
from .subtitle_download import fetch


class SubtitleWorkspacePlugin(PluginBase):
    """Manual sidecar subtitle workspace backed by configured media directories."""

    manifest = MANIFEST

    def __init__(self) -> None:
        self._sessions = SubtitleSessions()

    async def on_event(self, event: PluginEvent, context: PluginContext) -> dict[str, Any]:
        selected = str(context.config.get("trigger_event") or "")
        if event.type not in self.manifest.events or event.type != selected:
            return {"status": "skipped", "reason": "event_not_selected"}
        identities = event_identities(event.data)
        if not identities:
            return {"status": "skipped", "reason": "missing_media_items"}
        identities = await self._supplement_event_identities(context, identities)
        results: list[dict[str, Any]] = []
        async with http_client(
            timeout=20,
            use_application_proxy=bool(context.config.get("online_use_proxy")),
        ) as client:
            service = self._online_service(client, context.config, getattr(context, "media_files", None))
            for identity in identities:
                results.append(await self._process_event_identity(context, service, identity))
        return await self._complete_event(context, results)

    async def _process_event_identity(
        self,
        context: PluginContext,
        service: OnlineSubtitleService,
        identity: MediaIdentity,
    ) -> dict[str, Any]:
        plan = build_search_plan(identity, season_pack=False)
        for warning in identity.warnings:
            context.logger.warning("字幕媒体身份冲突，保留事件字段：%s", warning)
        if plan.errors:
            return self._event_skip_result(identity, plan.errors[0], failed=1)
        if self._skip_chinese_event_media(context, identity):
            return self._event_skip_result(identity, "chinese_media", failed=0)
        target = identity.as_dict()
        target["keyword"] = plan.queries[0].keyword
        search_languages = self._search_languages(context.config)
        requests = [
            self._search_request(identity, query, search_languages) for query in plan.queries
        ]
        threshold = min(100.0, max(0.0, float(context.config.get("auto_match_score") or 75)))
        outcome: dict[str, Any] = {
            "media_path": target["media_path"],
            "saved": [],
            "skipped": 0,
            "failed": 0,
            "details": [],
            "errors": [],
        }
        candidate_count = eligible_count = 0
        source_errors: list[dict[str, Any]] = []
        async for report in service.search_sequential(requests):
            candidate_count += len(report.candidates)
            source_errors.extend(self._error_dict(item) for item in report.errors)
            candidates = [
                item for item in report.candidates if item.downloadable and item.score >= threshold
            ][:1]
            eligible_count += len(candidates)
            if not candidates:
                continue
            attempt = await save_candidates(
                context, target, candidates, downloader=service.download
            )
            self._merge_event_attempt(outcome, attempt)
            if attempt.get("saved"):
                outcome.pop("reason", None)
                break
        return self._event_outcome(
            identity, outcome, candidate_count, eligible_count, source_errors
        )

    @staticmethod
    def _event_outcome(
        identity: MediaIdentity,
        outcome: dict[str, Any],
        candidate_count: int,
        eligible_count: int,
        source_errors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            **outcome,
            "title": identity.title,
            "candidate_count": candidate_count,
            "eligible_count": eligible_count,
            "source_errors": source_errors,
            "identity_warnings": list(identity.warnings),
        }

    @staticmethod
    def _merge_event_attempt(outcome: dict[str, Any], attempt: dict[str, Any]) -> None:
        for key in ("saved", "details", "errors"):
            outcome[key].extend(attempt.get(key, []))
        for key in ("skipped", "failed"):
            outcome[key] += attempt.get(key, 0)
        if attempt.get("reason"):
            outcome["reason"] = attempt["reason"]

    @staticmethod
    def _event_skip_result(identity: MediaIdentity, reason: str, *, failed: int) -> dict[str, Any]:
        return {
            "title": identity.title,
            "media_path": identity.media_path,
            "saved": [],
            "failed": failed,
            "candidate_count": 0,
            "reason": reason,
            "identity_warnings": list(identity.warnings),
        }

    @staticmethod
    def _skip_chinese_event_media(context: PluginContext, identity: MediaIdentity) -> bool:
        chinese_languages = {
            "zh",
            "zh-cn",
            "zh-tw",
            "zh-hans",
            "zh-hant",
            "cmn",
            "yue",
        }
        return bool(
            context.config.get("auto_skip_chinese_media_on_transfer", True)
            and identity.original_language in chinese_languages
        )

    async def _complete_event(
        self, context: PluginContext, results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        candidate_count = sum(item["candidate_count"] for item in results)
        saved_count = sum(len(item["saved"]) for item in results)
        failed_count = sum(item["failed"] for item in results)
        context.logger.info(
            "事件字幕处理完成：媒体 %s，保存 %s，候选失败 %s",
            len(results),
            saved_count,
            failed_count,
        )
        if context.config.get("notification_enabled", False):
            await context.notifications.send(
                "事件字幕处理完成",
                (
                    f"处理媒体 {len(results)} 个，保存字幕 {saved_count} 份，"
                    f"候选失败 {failed_count} 个。"
                ),
            )
        return {
            "media_count": len(results),
            "candidate_count": candidate_count,
            "saved_count": saved_count,
            "failed_count": failed_count,
            "items": results,
            "statistics": summarize(results),
        }

    async def run(self, context: PluginContext) -> dict[str, Any]:
        catalog = await self._catalog(context, query="", limit=200, include_subtitles=True)
        subtitle_count = sum(len(item.get("subtitles") or []) for item in catalog["items"])
        context.logger.info(
            "字幕目录检查完成：媒体 %s，外挂字幕 %s",
            len(catalog["items"]),
            subtitle_count,
        )
        if bool(context.config.get("notification_enabled")):
            await context.notifications.send(
                "字幕目录检查完成",
                (f"检查媒体 {len(catalog['items'])} 个，发现外挂字幕 {subtitle_count} 个。"),
                notification_type="plugin",
            )
        return {"media_count": len(catalog["items"]), "subtitle_count": subtitle_count}

    async def handle_api(
        self,
        request: PluginApiRequest,
        context: PluginContext,
    ) -> dict[str, Any]:
        if request.action in {"catalog", "detail", "inventory", "poster", "upload", "delete", "adjust"}:
            return await self._handle_file_api(request, context)
        if request.action in {
            "online",
            "online-search",
            "online-preview",
            "online-confirm",
            "online-captcha",
        }:
            return await self._handle_online_api(request, context)
        raise KeyError("字幕插件页面操作不存在")

    async def _handle_file_api(
        self, request: PluginApiRequest, context: PluginContext
    ) -> dict[str, Any]:
        if request.action == "catalog" and request.method == "GET":
            return await self._catalog(
                context,
                query=request.query.get("query", ""),
                limit=min(200, max(1, int(request.query.get("limit", "80") or 80))),
                offset=max(0, int(request.query.get("offset", "0") or 0)),
            )
        if request.action == "detail" and request.method == "GET":
            row = await context.media_files.recorded_detail(request.query.get("media_path", ""))
            return {**row, "identity": catalog_identity(row).as_dict()}
        if request.action == "inventory" and request.method == "GET":
            return await context.media_files.subtitles(request.query.get("media_path", ""))
        if request.action == "poster" and request.method == "GET":
            return await context.media_files.poster(request.query.get("media_path", ""))
        if request.action == "upload" and request.method == "POST":
            return await self._upload_subtitle(request, context)
        if request.action == "delete" and request.method == "POST":
            result = await context.media_files.delete_subtitle(
                str(request.payload.get("media_path") or ""),
                str(request.payload.get("subtitle_name") or ""),
            )
            await self._notify_file_action(context, "字幕已删除", result)
            return result
        if request.action == "adjust" and request.method == "POST":
            return await self._adjust_subtitle(request, context)
        raise KeyError("字幕插件页面操作不存在")

    async def _handle_online_api(
        self, request: PluginApiRequest, context: PluginContext
    ) -> dict[str, Any]:
        if request.action == "online" and request.method == "GET":
            return await self._search_online(
                context,
                media_path=request.query.get("media_path", ""),
                query=request.query.get("query", ""),
                season_pack=False,
            )
        if request.action == "online-search" and request.method == "POST":
            return await self._search_online(
                context,
                media_path=str(request.payload.get("media_path") or ""),
                query=str(request.payload.get("query") or ""),
                season_pack=bool(request.payload.get("season_pack", False)),
            )
        if request.action == "online-preview" and request.method == "POST":
            return await self._preview_online(request, context)
        if request.action == "online-confirm" and request.method == "POST":
            return await self._confirm_online(request, context)
        if request.action == "online-captcha" and request.method == "POST":
            return await self._submit_captcha(request, context)
        raise KeyError("字幕插件页面操作不存在")

    @staticmethod
    async def _upload_subtitle(request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        media_path = request.query.get("media_path", "")
        in_history = await context.organizer.has_successful_destination(media_path)
        if not in_history and not await context.media_files.is_catalog_media(media_path):
            raise ValueError("只能为同步或整理目录中的媒体上传字幕")
        filename = unquote(str(request.filename or "")).strip()
        extension = Path(filename).suffix.casefold().lstrip(".")
        content = request.content
        if extension in {"webvtt", "sbv", "sub"}:
            from .subtitle_files import output_format, subtitle_text

            content = subtitle_text(content, extension).encode("utf-8")
            extension = output_format(extension)
        language = request.query.get("language") or "auto"
        if language == "auto":
            from .subtitle_files import subtitle_text
            from .subtitle_priority import detect_language

            text = subtitle_text(content, extension)
            language = detect_language(filename, text, extension)
            if language == "und":
                raise ValueError("无法可靠识别字幕语言，请手动选择语言后重新上传")
        overwrite = request.query.get("overwrite", "").casefold() in {
            "1",
            "true",
            "yes",
        }
        if "overwrite" not in request.query:
            overwrite = bool(context.config.get("overwrite_existing", False))
        result = await context.media_files.write_subtitle(
            media_path,
            content,
            extension=extension,
            language=language,
            overwrite=overwrite,
        )
        await SubtitleWorkspacePlugin._notify_file_action(context, "字幕已保存", result)
        return result

    @staticmethod
    async def _adjust_subtitle(request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        offset_seconds = float(request.payload.get("offset_seconds") or 0)
        configured_limit = float(context.config.get("timeline_max_offset_seconds") or 120)
        if abs(offset_seconds) > min(300, max(1, configured_limit)):
            raise ValueError(f"字幕时间偏移不能超过当前设置的 {configured_limit:g} 秒")
        result = await context.media_files.adjust_subtitle(
            str(request.payload.get("media_path") or ""),
            str(request.payload.get("subtitle_name") or ""),
            offset_seconds=offset_seconds,
        )
        await SubtitleWorkspacePlugin._notify_file_action(context, "字幕调轴完成", result)
        return result

    @staticmethod
    async def _notify_file_action(
        context: PluginContext,
        title: str,
        result: dict[str, Any],
    ) -> None:
        config = getattr(context, "config", {})
        if not isinstance(config, dict) or not bool(config.get("notification_enabled")):
            return
        target = str(result.get("subtitle_path") or result.get("subtitle_name") or "")
        await context.notifications.send(
            title,
            target,
            notification_type="plugin",
        )

    @staticmethod
    def _online_service(client: Any, config: dict[str, Any], media_files: Any = None) -> OnlineSubtitleService:
        enabled = config.get("online_providers")
        providers = (
            [str(item) for item in enabled] if isinstance(enabled, list) else ["subhd", "zimuku"]
        )
        if {"shooter", "xunlei"}.issubset(providers):
            from .shared_samples import SharedVideoSamples
            media_files = SharedVideoSamples(media_files)
        factories: dict[str, Callable[[Any, dict[str, Any]], OnlineSource]] = {
            "subdl": SubDLSource,
            "shooter": lambda client, config: ShooterSource(client, config, media_files),
            "xunlei": lambda client, config: XunleiSource(client, config, media_files),
            "assrt": AssrtSource,
            "opensubtitles": OpenSubtitlesSource,
            "subhd": SubHDSource,
            "zimuku": ZimukuSource,
        }
        sources = [factories[key](client, config) for key in providers if key in factories]
        return OnlineSubtitleService(sources, timeout=12, retries=1)

    @staticmethod
    def _search_languages(config: dict[str, Any]) -> str:
        configured = config.get("auto_subtitle_language_priority")
        values = configured if isinstance(configured, list) else ["zh-CN", "zh-TW", "zh", "en"]
        aliases = {
            "zh-cn-en": ("ze",),
            "zh-tw-en": ("ze",),
            "zh-cn": ("zh-cn",),
            "zh-hans": ("zh-cn",),
            "zh-tw": ("zh-tw",),
            "zh-hant": ("zh-tw",),
            "zh-ca": ("zh-ca",),
            "zh": ("zh-cn", "zh-tw", "zh-ca", "ze"),
            "ze": ("ze",),
            "en": ("en",),
            "eng": ("en",),
            "ja": ("ja",),
            "ko": ("ko",),
        }
        result: list[str] = []
        for value in values:
            normalized = str(value).strip().casefold().replace("_", "-")
            for code in aliases.get(normalized, ()):
                if code not in result:
                    result.append(code)
        return ",".join(result)

    @staticmethod
    def _search_request(identity: Any, query: SearchQuery, language: str) -> SearchRequest:
        return SearchRequest(
            query=query.keyword,
            identity=identity,
            language=language,
            season=query.season,
            episode=query.episode,
            year=query.year,
            tmdb_id=query.tmdb_id,
            imdb_id=query.imdb_id,
            douban_id=query.douban_id,
        )

    @staticmethod
    async def _supplement_event_identities(
        context: PluginContext, identities: list[MediaIdentity]
    ) -> list[MediaIdentity]:
        media_files = getattr(context, "media_files", None)
        catalog_method = getattr(media_files, "catalog", None)
        if not callable(catalog_method):
            return identities
        try:
            catalog = await catalog_method(query="", limit=500)
            if not isinstance(catalog, dict):
                raise ValueError("目录接口未返回有效结果")
        except (OSError, TypeError, ValueError) as error:
            context.logger.warning("字幕目录身份补全失败，将使用事件身份：%s", error)
            return [
                identity_with_warning(identity, "identity_supplement_failed")
                for identity in identities
            ]
        rows = {
            media_path_key(str(item.get("path") or "")): item
            for item in catalog.get("items", [])
            if isinstance(item, dict) and item.get("path")
        }
        completed: list[MediaIdentity] = []
        for identity in identities:
            row = rows.get(media_path_key(identity.media_path))
            if not row:
                completed.append(identity)
                continue
            raw_identity = row.get("identity")
            supplement = raw_identity if isinstance(raw_identity, dict) else row
            completed.append(supplement_identity(identity, supplement))
        return completed

    @staticmethod
    def _queries_for_search(
        identity: MediaIdentity,
        queries: list[SearchQuery],
        edited: str,
        *,
        season_pack: bool,
    ) -> list[SearchQuery]:
        if not edited:
            return queries
        if identity.is_episode:
            token = (
                f"S{identity.season:02d}"
                if season_pack
                else f"S{identity.season:02d}E{identity.episode:02d}"
            )
            edited = re.sub(
                r"(?i)(?<![A-Z0-9])S\d{1,2}(?:[ ._-]*E\d{1,4})?(?!\d)",
                " ",
                edited,
            )
            edited = f"{' '.join(edited.split())} {token}".strip()
        return [
            SearchQuery(
                keyword=edited,
                title=identity.title,
                year=identity.year,
                season=identity.season,
                episode=None if season_pack else identity.episode,
                tmdb_id=identity.tmdb_id,
                imdb_id=identity.imdb_id,
                douban_id=identity.douban_id,
            )
        ]

    async def _search_online(
        self,
        context: PluginContext,
        *,
        media_path: str,
        query: str,
        season_pack: bool,
        cookies: Any = None,
    ) -> dict[str, Any]:
        identity = await self._catalog_media_identity(context, media_path)
        queries = self._validated_search_queries(identity, query, season_pack)
        search_languages = self._search_languages(context.config)
        requests = [self._search_request(identity, item, search_languages) for item in queries]
        client_options: dict[str, Any] = {
            "timeout": 20,
            "use_application_proxy": bool(context.config.get("online_use_proxy")),
        }
        if cookies is not None:
            client_options["cookies"] = cookies
        async with http_client(**client_options) as client:
            report = await self._online_service(client, context.config, getattr(context, "media_files", None)).search(requests)
        presenter = SearchResultPresenter(
            remember_candidate=lambda candidate: self._remember_candidate(
                context, identity.media_path, candidate
            ),
            remember_challenge=lambda challenge: self._search_challenge(
                context, challenge, media_path, query, season_pack
            ),
            error_dict=self._error_dict,
            fallback_actions=lambda: self._manual_search_actions(
                context.config, queries[0].keyword
            ),
        )
        return {
            "identity": identity.as_dict(),
            "queries": [item.parameters() for item in queries],
            **presenter.present(report),
        }

    def _validated_search_queries(
        self,
        identity: MediaIdentity,
        query: str,
        season_pack: bool,
    ) -> list[SearchQuery]:
        plan = build_search_plan(identity, season_pack=season_pack)
        if plan.errors:
            labels = {
                "missing_title": "缺少媒体标题",
                "missing_season": "缺少季信息",
                "missing_episode": "缺少集信息",
            }
            raise ValueError(labels.get(plan.errors[0], "媒体身份不完整"))
        return self._queries_for_search(
            identity,
            list(plan.queries),
            query.strip(),
            season_pack=season_pack,
        )

    def _search_challenge(
        self,
        context: PluginContext,
        challenge: CaptchaChallenge,
        media_path: str,
        query: str,
        season_pack: bool,
    ) -> dict[str, Any]:
        handle = self._remember_captcha(
            context,
            challenge,
            extra_context={
                "flow": "zimuku-search",
                "media_path": media_path,
                "query": query,
                "season_pack": season_pack,
            },
        )
        return self._captcha_public(handle, challenge)

    @staticmethod
    def _manual_search_actions(config: dict[str, Any], keyword: str) -> list[dict[str, str]]:
        encoded = quote_plus(keyword)
        enabled = config.get("online_providers")
        providers = enabled if isinstance(enabled, list) else ["subhd", "zimuku"]
        definitions = {
            "assrt": (
                "ASSRT",
                f"{str(config.get('assrt_search_url') or 'https://2.assrt.net').rstrip('/')}/search?keyword={encoded}",
            ),
            "opensubtitles": (
                "OpenSubtitles",
                f"https://www.opensubtitles.com/zh-CN/search-all/q-{encoded}",
            ),
            "subhd": (
                "SubHD",
                f"{str(config.get('subhd_url') or 'https://subhd.tv').rstrip('/')}/search/{encoded}",
            ),
            "zimuku": (
                "字幕库",
                f"{str(config.get('zimuku_url') or 'https://zmk.pw').rstrip('/')}/search?q={encoded}",
            ),
        }
        actions: list[dict[str, str]] = []
        for key in providers:
            if key not in definitions:
                continue
            provider, raw_url = definitions[key]
            url = safe_public_link(raw_url)
            if url:
                actions.append({"provider": provider, "url": url, "reason": "自动搜索暂无结果"})
        return actions

    async def _preview_online(
        self, request: PluginApiRequest, context: PluginContext
    ) -> dict[str, Any]:
        media_path = str(request.payload.get("media_path") or "")
        token = str(
            request.payload.get("candidate_handle") or request.payload.get("candidate_token") or ""
        )
        identity = await self._catalog_media_identity(context, media_path)
        candidate = self._load_candidate(context, token, identity.media_path)
        target = identity.as_dict()
        if identity.is_episode:
            target["keyword"] = f"{identity.title} S{identity.season:02d}E{identity.episode:02d}"
        else:
            target["keyword"] = identity.title
        async with http_client(
            timeout=30,
            use_application_proxy=bool(context.config.get("online_use_proxy")),
        ) as client:
            downloaded = await self._online_service(client, context.config, getattr(context, "media_files", None)).download(candidate)
        if downloaded.error:
            challenge = getattr(downloaded.error, "challenge", None)
            if isinstance(challenge, CaptchaChallenge):
                handle = self._remember_captcha(
                    context,
                    challenge,
                    extra_context={
                        "media_path": identity.media_path,
                        "candidate": self._candidate_payload(candidate),
                    },
                )
                return {
                    "captcha_required": True,
                    "captcha": self._captcha_public(handle, challenge),
                    "candidate_handle": token,
                }
            raise ValueError(downloaded.error.message)
        return await self._preview_from_download(context, identity, candidate, downloaded)

    async def _preview_from_download(
        self,
        context: PluginContext,
        identity: MediaIdentity,
        candidate: SourceCandidate,
        downloaded: Any,
    ) -> dict[str, Any]:
        try:
            previews = prepare_previews(context.config, identity, candidate, downloaded)
        except ValueError:
            if candidate.provider == "SubDL" and str(candidate.language).casefold() in {
                "zh", "zh-cn", "zh-tw", "zh-hans", "zh-hant"
            }:
                raise ValueError(
                    "SubDL 将该文件标记为中文字幕，但源文件的语言或文本编码无效"
                ) from None
            raise
        preview = SubtitlePreviewStore().create(identity.media_path, previews)
        preview["preview_handle"] = preview.pop("preview_token")
        return preview

    async def _submit_captcha(
        self, request: PluginApiRequest, context: PluginContext
    ) -> dict[str, Any]:
        token = str(
            request.payload.get("captcha_handle") or request.payload.get("captcha_token") or ""
        )
        code = str(request.payload.get("code") or "").strip()
        if not token or not code:
            raise ValueError("验证码会话或输入内容不完整")
        if len(code) > 64:
            raise ValueError("验证码长度无效")
        challenge = self._load_captcha(context, token)
        flow = str((challenge.get("context") or {}).get("flow") or challenge.get("site") or "")
        if challenge.get("site") == "zimuku" and flow == "zimuku-search":
            return await self._solve_zimuku_search(context, challenge, code)
        if challenge.get("site") == "subhd" and flow == "subhd-download":
            return await self._solve_subhd_download(context, challenge, code, token)
        raise ValueError("该验证码会话暂不支持自动提交")

    async def _solve_zimuku_search(
        self,
        context: PluginContext,
        challenge: dict[str, Any],
        code: str,
    ) -> dict[str, Any]:
        resume = challenge.get("context") or {}
        media_path = str(resume.get("media_path") or "")
        query = str(resume.get("query") or "")
        season_pack = bool(resume.get("season_pack", False))
        if not media_path:
            raise ValueError("字幕库验证码会话已过期，请重新搜索")
        cookies = cookies_from_snapshot(challenge.get("cookies") or ())
        verify_url = str(challenge.get("verification_url") or challenge.get("submit_url") or "")
        if not verify_url:
            raise ValueError("字幕库验证码提交地址缺失，请重新搜索")
        param = str((challenge.get("payload") or {}).get("param") or "security_verify_img")
        encoded = encode_captcha_code(code, str(challenge.get("code_encoding") or "plain"))
        separator = "&" if "?" in verify_url else "?"
        submit_url = f"{verify_url}{separator}{quote_plus(param)}={quote_plus(encoded)}"
        client_options: dict[str, Any] = {
            "timeout": 20,
            "use_application_proxy": bool(context.config.get("online_use_proxy")),
            "cookies": cookies,
        }
        async with http_client(**client_options) as client:
            try:
                await fetch(client, submit_url)
            except Exception:
                # Zimuku sometimes still returns the verify page for a stale
                # submission. Re-running the search below is the authoritative
                # check and produces the next challenge if needed.
                pass
            resumed_cookies = cookies_from_snapshot(cookie_snapshot(client))
        return await self._search_online(
            context,
            media_path=media_path,
            query=query,
            season_pack=season_pack,
            cookies=resumed_cookies,
        )

    async def _solve_subhd_download(
        self,
        context: PluginContext,
        challenge: dict[str, Any],
        code: str,
        original_token: str,
    ) -> dict[str, Any]:
        resume = challenge.get("context") or {}
        media_path = str(resume.get("media_path") or "")
        candidate_payload = resume.get("candidate")
        sid = str(resume.get("sid") or "")
        down_url = str(resume.get("down_url") or "")
        referer = str(resume.get("referer") or down_url or "")
        if not media_path or not isinstance(candidate_payload, dict) or not sid or not down_url:
            raise ValueError("SubHD 验证码会话已过期，请重新预览")
        identity = await self._catalog_media_identity(context, media_path)
        candidate = SourceCandidate(**candidate_payload)
        cookies = cookies_from_snapshot(challenge.get("cookies") or ())
        client_options: dict[str, Any] = {
            "timeout": 30,
            "use_application_proxy": bool(context.config.get("online_use_proxy")),
            "cookies": cookies,
        }
        async with http_client(**client_options) as client:
            source = SubHDSource(client, context.config)
            downloaded = await source.submit_download_captcha(
                sid=sid,
                down_url=down_url,
                referer=referer,
                code=code,
                result_id=candidate.result_id,
            )
        required = self._download_challenge(
            context, downloaded, media_path, candidate_payload, original_token
        )
        if required is not None:
            return required
        return await self._preview_from_download(context, identity, candidate, downloaded)

    def _download_challenge(
        self,
        context: PluginContext,
        downloaded: Any,
        media_path: str,
        candidate_payload: dict[str, Any],
        original_token: str,
    ) -> dict[str, Any] | None:
        if downloaded.error:
            next_challenge = getattr(downloaded.error, "challenge", None)
            if isinstance(next_challenge, CaptchaChallenge):
                handle = self._remember_captcha(
                    context,
                    next_challenge,
                    extra_context={
                        "media_path": media_path,
                        "candidate": candidate_payload,
                    },
                )
                return {
                    "captcha_required": True,
                    "captcha": self._captcha_public(handle, next_challenge),
                    "candidate_handle": original_token,
                }
            raise ValueError(downloaded.error.message)
        return None

    async def _confirm_online(
        self, request: PluginApiRequest, context: PluginContext
    ) -> dict[str, Any]:
        media_path = str(request.payload.get("media_path") or "")
        identity = await self._catalog_media_identity(context, media_path)
        raw_selected = request.payload.get("selected")
        try:
            selected = (
                [int(item) for item in raw_selected] if isinstance(raw_selected, list) else None
            )
        except (TypeError, ValueError) as error:
            raise ValueError("请选择有效的字幕预览项") from error
        files = SubtitlePreviewStore().consume(
            str(
                request.payload.get("preview_handle") or request.payload.get("preview_token") or ""
            ),
            identity.media_path,
            selected,
        )
        saved = []
        errors = []
        for item in files:
            try:
                saved.append(
                    await context.media_files.write_subtitle(
                        identity.media_path,
                        item.content,
                        extension=item.extension,
                        language=item.language,
                        overwrite=bool(context.config.get("overwrite_existing", False)),
                    )
                )
            except (OSError, ValueError) as error:
                errors.append(str(error))
        if not saved:
            raise ValueError(errors[0] if errors else "没有保存任何字幕")
        return {"saved": saved, "errors": errors}

    async def _catalog_media_identity(self, context: PluginContext, media_path: str):
        row = await context.media_files.recorded_detail(media_path)
        return catalog_identity(row)

    def _remember_candidate(
        self, context: PluginContext, media_path: str, candidate: SourceCandidate
    ) -> str:
        return self._sessions.remember_candidate(context, media_path, candidate)

    def _load_candidate(
        self, context: PluginContext, token: str, media_path: str
    ) -> SourceCandidate:
        return self._sessions.load_candidate(context, token, media_path)

    def _remember_captcha(
        self,
        context: PluginContext,
        challenge: CaptchaChallenge | dict[str, Any],
        *,
        extra_context: dict[str, Any] | None = None,
    ) -> str:
        return self._sessions.remember_captcha(context, challenge, extra_context=extra_context)

    def _load_captcha(self, context: PluginContext, token: str) -> dict[str, Any]:
        return self._sessions.load_captcha(context, token)

    _captcha_public = staticmethod(SubtitleSessions.captcha_public)
    _candidate_payload = staticmethod(SubtitleSessions.candidate_payload)

    @staticmethod
    def _error_dict(error: Any) -> dict[str, Any]:
        return {
            "provider": error.provider,
            "kind": error.kind.value,
            "message": error.message,
            "retryable": error.retryable,
            "manual_url": safe_public_link(error.manual_url),
        }

    async def _catalog(
        self,
        context: PluginContext,
        *,
        query: str,
        limit: int,
        offset: int = 0,
        include_subtitles: bool = False,
    ) -> dict[str, Any]:
        catalog = await context.media_files.recorded_catalog(
            query=str(query or ""), limit=limit, offset=offset
        )
        items: list[dict[str, Any]] = []
        for row in catalog.get("items") or []:
            item = {**row, "identity": catalog_identity(row).as_dict()}
            if include_subtitles:
                try:
                    inventory = await context.media_files.subtitles(str(row["path"]))
                except (FileNotFoundError, OSError, ValueError):
                    continue
                item["subtitles"] = list(inventory.get("items") or [])
            items.append(item)
        return {**catalog, "items": items, "count": len(items)}



Plugin = SubtitleWorkspacePlugin
PLUGIN = SubtitleWorkspacePlugin
