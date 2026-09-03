from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.modules.plugins.contracts import PluginBase, PluginContext, PluginManifest
from app.modules.plugins.permissions import PluginPermission


_HAN = re.compile(r"[\u3400-\u9fff]")
_SPACE = re.compile(r"\s+")


@dataclass(slots=True)
class _RunState:
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    updated_people: set[str] = field(default_factory=set)
    scanned_media: int = 0
    scanned_people: int = 0
    updated_media: int = 0
    updated_profiles: int = 0
    updated_images: int = 0
    removed_people: int = 0
    failures: int = 0

    def result(self) -> dict[str, Any]:
        return {
            "scanned_media": self.scanned_media,
            "scanned_people": self.scanned_people,
            "updated_media": self.updated_media,
            "updated_profiles": self.updated_profiles,
            "updated_images": self.updated_images,
            "removed_people": self.removed_people,
            "failures": self.failures,
        }


class CastProfileEnricherPlugin(PluginBase):
    """Complete localized cast and crew data through the public plugin SDK."""

    manifest = PluginManifest(
        entrypoint="plugin:CastProfileEnricherPlugin",
        id="cast-profile-enricher",
        name="演职员资料完善",
        version="1.0.0",
        description="为媒体服务器中的演员和主创补充中文姓名、角色说明、人物简介与头像。",
        icon="mdi-account-details-outline",
        permissions=(
            PluginPermission.MEDIA_SERVER_READ,
            PluginPermission.MEDIA_SERVER_WRITE_METADATA,
            PluginPermission.MEDIA_SERVER_WRITE_IMAGES,
            PluginPermission.MEDIA_DISCOVER,
        ),
        capabilities=("metadata_enricher", "media_server_controller", "scheduled_task"),
        schedule_seconds=24 * 60 * 60,
        config_schema={
            "sections": [
                {
                    "key": "run",
                    "title": "执行设置",
                    "description": "选择自动执行方式和需要维护的媒体服务器。",
                },
                {
                    "key": "policy",
                    "title": "完善规则",
                    "description": "控制需要处理的人物范围以及允许写入的内容。",
                },
            ],
            "fields": [
                {
                    "key": "enabled",
                    "input_type": "switch",
                    "label": "启用每日维护",
                    "default": False,
                    "icon": "mdi-calendar-refresh-outline",
                    "section": "run",
                },
                {
                    "key": "cron",
                    "input_type": "cron",
                    "label": "执行周期",
                    "default": "",
                    "placeholder": "5位cron表达式，留空自动",
                    "icon": "mdi-calendar-clock",
                    "section": "run",
                },
                {
                    "key": "selected_servers",
                    "input_type": "resource_multi_select",
                    "resource_kind": "media_server",
                    "required_capabilities": ["read", "write_metadata"],
                    "label": "媒体服务器",
                    "default": [],
                    "description": "未选择时处理全部已启用的媒体服务器。",
                    "section": "run",
                },
                {
                    "key": "condition",
                    "input_type": "select",
                    "label": "处理范围",
                    "default": "missing_any",
                    "icon": "mdi-filter-outline",
                    "section": "policy",
                    "options": [
                        {"value": "all", "label": "全部人物"},
                        {"value": "missing_any", "label": "姓名或角色未中文化"},
                        {"value": "missing_name", "label": "姓名未中文化"},
                        {"value": "missing_role", "label": "角色未中文化"},
                    ],
                },
                {
                    "key": "metadata_priority",
                    "input_type": "select",
                    "label": "资料优先级",
                    "default": "tmdb_douban",
                    "icon": "mdi-database-search-outline",
                    "section": "policy",
                    "options": [
                        {"value": "tmdb_douban", "label": "TMDB 优先，豆瓣补充"},
                        {"value": "douban_tmdb", "label": "豆瓣优先，TMDB 补充"},
                    ],
                },
                {
                    "key": "update_biography",
                    "input_type": "switch",
                    "label": "补充人物简介",
                    "default": True,
                    "icon": "mdi-text-account",
                    "section": "policy",
                },
                {
                    "key": "update_images",
                    "input_type": "switch",
                    "label": "补充人物头像",
                    "default": True,
                    "icon": "mdi-account-box-outline",
                    "section": "policy",
                },
                {
                    "key": "remove_unresolved",
                    "input_type": "switch",
                    "label": "移除无法完善的人物",
                    "default": False,
                    "description": "仅在两个资料源均无法找到可靠匹配时移除，默认关闭。",
                    "icon": "mdi-account-remove-outline",
                    "section": "policy",
                },
            ],
        },
    )

    async def run(self, context: PluginContext) -> dict[str, Any]:
        if not bool(context.config.get("enabled", False)):
            return {"status": "disabled", **_RunState().result()}
        state = _RunState()
        server_ids = await self._server_ids(context)
        for server_id in server_ids:
            await self._process_server(context, state, server_id)
        result = state.result()
        context.logger.info(
            "演职员资料维护完成：媒体 %s，人物 %s，更新媒体 %s，更新人物 %s，失败 %s",
            state.scanned_media,
            state.scanned_people,
            state.updated_media,
            state.updated_profiles,
            state.failures,
        )
        return result

    async def _server_ids(self, context: PluginContext) -> list[str]:
        selected = self._strings(context.config.get("selected_servers"))
        if selected:
            return selected
        payload = await context.media_servers.configurations()
        return [
            str(item.get("id") or "")
            for item in payload.get("items") or []
            if item.get("enabled") and item.get("id")
        ]

    async def _process_server(
        self,
        context: PluginContext,
        state: _RunState,
        server_id: str,
    ) -> None:
        try:
            libraries = await context.media_servers.libraries(server_id)
        except Exception as error:
            state.failures += 1
            context.logger.warning("媒体服务器读取失败：%s", error)
            return
        for library in libraries.get("items") or []:
            library_id = str(library.get("id") or "")
            if library_id:
                await self._process_library(context, state, server_id, library_id)

    async def _process_library(
        self,
        context: PluginContext,
        state: _RunState,
        server_id: str,
        library_id: str,
    ) -> None:
        start = 0
        while True:
            page = await context.media_servers.metadata_items(
                server_id,
                library_id,
                start=start,
                limit=200,
                include_types=("Movie", "Series"),
            )
            items = list(page.get("items") or [])
            for item in items:
                await self._process_media(context, state, server_id, item)
            start += len(items)
            if not items or start >= int(page.get("total") or 0):
                return

    async def _process_media(
        self,
        context: PluginContext,
        state: _RunState,
        server_id: str,
        media: dict[str, Any],
    ) -> None:
        state.scanned_media += 1
        original_people = list(media.get("people") or [])
        changed_people: list[dict[str, Any]] = []
        changed = False
        for person in original_people:
            state.scanned_people += 1
            updated = await self._process_person(context, state, server_id, media, person)
            if updated is None:
                changed = True
                state.removed_people += 1
                continue
            changed_people.append(updated)
            changed = changed or updated != person
        if changed and media.get("id"):
            try:
                await context.media_servers.update_item_metadata(
                    server_id,
                    str(media["id"]),
                    {"People": changed_people},
                )
                state.updated_media += 1
            except Exception as error:
                state.failures += 1
                context.logger.warning("媒体人物列表更新失败：%s - %s", media.get("name"), error)

    async def _process_person(
        self,
        context: PluginContext,
        state: _RunState,
        server_id: str,
        media: dict[str, Any],
        person: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self._eligible(context, person):
            return person
        profile = await self._profile(context, state, server_id, person)
        localized_name = self._localized_name(profile)
        localized_role = self._localized_role(profile, media)
        if not localized_name and not localized_role:
            can_remove = bool(context.config.get("remove_unresolved", False)) and bool(
                profile.get("_lookup_complete", False)
            )
            return None if can_remove else person
        updated = dict(person)
        if localized_name:
            updated["Name"] = localized_name
        if localized_role:
            updated["Role"] = localized_role
        await self._update_profile_item(context, state, server_id, person, profile, localized_name)
        return updated

    async def _profile(
        self,
        context: PluginContext,
        state: _RunState,
        server_id: str,
        person: dict[str, Any],
    ) -> dict[str, Any]:
        key = str(person.get("Id") or self._key(person.get("Name")))
        if key in state.profiles:
            return state.profiles[key]
        metadata: dict[str, Any] = {}
        if person.get("Id"):
            try:
                metadata = await context.media_servers.item_metadata(server_id, str(person["Id"]))
            except Exception:
                metadata = {}
        profile = await self._resolve_sources(context, person, metadata)
        state.profiles[key] = profile
        return profile

    async def _resolve_sources(
        self,
        context: PluginContext,
        person: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        priority = str(context.config.get("metadata_priority") or "tmdb_douban")
        sources = ("douban", "tmdb") if priority == "douban_tmdb" else ("tmdb", "douban")
        name = str(person.get("Name") or metadata.get("name") or "").strip()
        profiles: list[dict[str, Any]] = []
        lookup_complete = True
        for source in sources:
            try:
                payload = await self._source_payload(context, source, name, metadata)
                if payload:
                    profiles.append(await context.media.person_detail(source, payload))
            except Exception:
                lookup_complete = False
        merged = self._merge_profiles(profiles)
        merged["_lookup_complete"] = lookup_complete
        merged["_locked_fields"] = list(metadata.get("locked_fields") or [])
        return merged

    async def _source_payload(
        self,
        context: PluginContext,
        source: str,
        name: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        provider_ids = dict(metadata.get("provider_ids") or {})
        direct_id = (
            str(provider_ids.get("Tmdb") or provider_ids.get("TMDB") or "")
            if source == "tmdb"
            else ""
        )
        if direct_id:
            return {"source_key": source, "source_id": direct_id, "name": name}
        result = await context.media.search_people(name, source=source, page=1)
        for item in result.get("items") or []:
            if self._person_matches(name, item):
                return dict(item)
        return {}

    async def _update_profile_item(
        self,
        context: PluginContext,
        state: _RunState,
        server_id: str,
        person: dict[str, Any],
        profile: dict[str, Any],
        localized_name: str,
    ) -> None:
        person_id = str(person.get("Id") or "")
        if not person_id or person_id in state.updated_people:
            return
        state.updated_people.add(person_id)
        changes = self._profile_changes(context, profile, localized_name)
        try:
            if changes:
                await context.media_servers.update_item_metadata(server_id, person_id, changes)
                state.updated_profiles += 1
            if bool(context.config.get("update_images", True)):
                await self._update_profile_image(context, state, server_id, person_id, profile)
        except Exception as error:
            state.failures += 1
            context.logger.debug("人物资料写入失败：%s - %s", person.get("Name"), error)

    async def _update_profile_image(
        self,
        context: PluginContext,
        state: _RunState,
        server_id: str,
        person_id: str,
        profile: dict[str, Any],
    ) -> None:
        image_url = str(profile.get("profile") or profile.get("poster") or "").strip()
        if not image_url:
            return
        content = await context.media.download_image(image_url)
        content_type = "image/png" if content.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
        await context.media_servers.set_primary_image(
            server_id,
            person_id,
            content,
            content_type=content_type,
        )
        state.updated_images += 1

    @staticmethod
    def _profile_changes(
        context: PluginContext,
        profile: dict[str, Any],
        localized_name: str,
    ) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        locked = [str(value) for value in profile.get("_locked_fields") or [] if value]
        if localized_name:
            changes["Name"] = localized_name
            if "Name" not in locked:
                locked.append("Name")
        biography = str(profile.get("biography") or "").strip()
        if bool(context.config.get("update_biography", True)) and biography:
            changes["Overview"] = biography
            if "Overview" not in locked:
                locked.append("Overview")
        if locked:
            changes["LockedFields"] = locked
        return changes

    @staticmethod
    def _merge_profiles(profiles: list[dict[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        aliases: list[str] = []
        works: list[dict[str, Any]] = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            for key, value in profile.items():
                if key not in {"also_known_as", "works"} and value and not merged.get(key):
                    merged[key] = value
            aliases.extend(str(value) for value in profile.get("also_known_as") or [] if value)
            works.extend(
                dict(value) for value in profile.get("works") or [] if isinstance(value, dict)
            )
        merged["also_known_as"] = list(dict.fromkeys(aliases))
        merged["works"] = works
        return merged

    def _eligible(self, context: PluginContext, person: dict[str, Any]) -> bool:
        condition = str(context.config.get("condition") or "missing_any")
        missing_name = not self._has_han(person.get("Name"))
        missing_role = str(person.get("Type") or "").casefold() == "actor" and not self._has_han(
            person.get("Role")
        )
        return {
            "all": True,
            "missing_name": missing_name,
            "missing_role": missing_role,
            "missing_any": missing_name or missing_role,
        }.get(condition, missing_name or missing_role)

    def _localized_name(self, profile: dict[str, Any]) -> str:
        values = [profile.get("name"), profile.get("title"), *(profile.get("also_known_as") or [])]
        for value in values:
            if self._has_han(value):
                return str(value).strip()[:256]
        return ""

    def _localized_role(self, profile: dict[str, Any], media: dict[str, Any]) -> str:
        provider_ids = {
            str(key).casefold(): str(value)
            for key, value in dict(media.get("provider_ids") or {}).items()
        }
        media_names = {self._key(media.get("name")), self._key(media.get("original_title"))} - {""}
        for work in profile.get("works") or []:
            work_id = str(
                work.get("source_id") or work.get("tmdb_id") or work.get("media_id") or ""
            )
            work_names = {self._key(work.get("title")), self._key(work.get("name"))} - {""}
            matches_id = work_id and work_id in set(provider_ids.values())
            if not matches_id and not media_names.intersection(work_names):
                continue
            role = str(work.get("character") or work.get("role") or "").strip()
            if self._has_han(role):
                return role[:256]
        return ""

    def _person_matches(self, expected: str, item: dict[str, Any]) -> bool:
        names = [item.get("name"), item.get("title"), *(item.get("also_known_as") or [])]
        expected_key = self._key(expected)
        return bool(expected_key and expected_key in {self._key(value) for value in names})

    @staticmethod
    def _has_han(value: object) -> bool:
        return bool(_HAN.search(str(value or "")))

    @staticmethod
    def _key(value: object) -> str:
        return _SPACE.sub("", str(value or "")).casefold()

    @staticmethod
    def _strings(value: object) -> list[str]:
        values = value if isinstance(value, (list, tuple, set)) else []
        return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))
