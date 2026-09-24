from __future__ import annotations

import re
import asyncio
import copy
from io import BytesIO
import time
from typing import Any

from app.modules.plugins.contracts import (
    PluginBase,
    PluginContext,
    PluginEvent,
)

from .manifest import manifest
from .event_refresh import SOURCE_EVENTS, schedule_refresh
from .run_state import RunState as _RunState
from .maintenance import Maintenance, SourceRequests, process_checkpoint
from .removal import can_remove, role_changes, annotate_profile


_HAN = re.compile(r"[\u3400-\u9fff]")
_SPACE = re.compile(r"\s+")


class CastProfileEnricherPlugin(PluginBase):
    """Complete localized cast and crew data through the public plugin SDK."""

    manifest = manifest

    async def on_lifecycle(
        self, event: str, context: PluginContext, previous_version: str = ""
    ) -> None:
        if event in {"install", "enable", "upgrade"}:
            await asyncio.to_thread(Maintenance, context, _RunState())

    async def run(self, context: PluginContext) -> dict[str, Any]:
        if getattr(context, "trigger", "manual") == "scheduled" and not bool(
            context.config.get("enabled", False)
        ):
            return {
                "status": "skipped",
                "reason": "scheduled_maintenance_disabled",
                **_RunState().result(),
            }
        return await self._run(context)

    async def handle_api(self, request: Any, context: PluginContext) -> dict[str, Any]:
        if request.action != "progress" or request.method.upper() != "GET":
            raise KeyError("未知的演职员维护接口")
        result = context.state.scoped("cast-maintenance-v2").get("progress") or {}
        if result.get("status") == "running" and result.get("started_at"):
            result["elapsed_seconds"] = max(0, int(time.time() - result["started_at"]))
        return result

    async def on_event(self, event: PluginEvent, context: PluginContext) -> dict[str, Any]:
        if event.type not in self.manifest.events:
            return {"status": "skipped", "reason": "unsupported_event"}
        selected_event = str(context.config.get("trigger_event") or "").strip()
        if not selected_event:
            return {"status": "skipped", "reason": "event_trigger_disabled"}
        if event.type in SOURCE_EVENTS:
            if event.type != selected_event:
                return {"status": "skipped", "reason": "event_not_selected"}
            if (
                event.type == "metadata.scrape.completed"
                and int(event.data.get("generated_files") or 0) <= 0
            ):
                return {"status": "skipped", "reason": "no_scraped_changes"}
            if not event.data.get("items"):
                return {"status": "skipped", "reason": "missing_media_items"}
            return schedule_refresh(context, event)
        if str(event.data.get("_source_event") or "") != selected_event:
            return {"status": "skipped", "reason": "event_not_selected"}
        targets = self._event_targets(event.data)
        if not targets:
            return {"status": "skipped", "reason": "missing_scraped_items"}
        return await self._run(context, targets=targets)

    async def _run(
        self,
        context: PluginContext,
        *,
        targets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        state = _RunState()
        context = copy.copy(context)
        state.maintenance = Maintenance(context, state, targets)
        context.media = SourceRequests(context.media, state.maintenance)
        try:
            try:
                server_ids = await self._server_ids(context)
                for server_id in server_ids:
                    await self._process_server(context, state, server_id, targets=targets)
            except BaseException:
                state.maintenance.finish("interrupted")
                raise
            status = (
                "partial"
                if state.failures or state.no_chinese_role or state.unmatched_people
                else "completed"
            )
            state.maintenance.finish(status)
            result = state.result()
            result["status"] = status
            context.logger.info(
                "演职员维护完成：媒体 %s，人物 %s，中文姓名 %s，中文角色 %s，简介 %s，头像 %s，失败 %s",
                state.scanned_media,
                state.scanned_people,
                state.updated_names,
                state.updated_roles,
                state.updated_biographies,
                state.updated_images,
                state.failures,
            )
            return result
        finally:
            context.media.cache.clear()
            context.media.cache_bytes = 0
            context.media = context.media.original
            state.maintenance = None
            for value in (state.profiles, state.casts, state.person_locks,
                          state.updated_people, state.changed_people, state.media_written,
                          state.retry_media):
                value.clear()

    def _event_targets(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        targets: list[dict[str, Any]] = []
        for value in data.get("items") or []:
            if not isinstance(value, dict):
                continue
            raw_identity = value.get("identity")
            identity = raw_identity if isinstance(raw_identity, dict) else {}
            target = dict(identity)
            path = str(value.get("relative_media_path") or "")
            if not str(target.get("title") or "").strip():
                title, year = self._identity_from_path(path)
                target["title"] = title
                target.setdefault("year", year)
            raw_external_ids = target.get("external_ids")
            external_ids = raw_external_ids if isinstance(raw_external_ids, dict) else {}
            if target.get("tmdb_id"):
                external_ids = {**external_ids, "tmdb": str(target["tmdb_id"])}
            if target.get("source_key") and target.get("source_id"):
                external_ids = {
                    **external_ids,
                    str(target["source_key"]): str(target["source_id"]),
                }
            target["external_ids"] = external_ids
            if target.get("title") or external_ids:
                targets.append(target)
        return targets

    @staticmethod
    def _identity_from_path(value: str) -> tuple[str, str]:
        parts = [part for part in value.replace("\\", "/").split("/") if part]
        if not parts:
            return "", ""
        stem = re.sub(r"\.[^.]+$", "", parts[-1])
        if re.search(r"(?i)S\d{1,2}E\d{1,3}", stem):
            candidates = [
                part
                for part in reversed(parts[:-1])
                if not re.fullmatch(r"(?i)(season|第)\s*\d+\s*(季)?", part)
            ]
            stem = candidates[0] if candidates else stem
        elif len(parts) > 1 and re.search(r"(?:19|20)\d{2}", parts[-2]):
            stem = parts[-2]
        year_match = re.search(r"(?:19|20)\d{2}", stem)
        year = year_match.group(0) if year_match else ""
        title = re.sub(r"[\[(（]?\s*(?:19|20)\d{2}\s*[\])）]?", "", stem)
        title = re.sub(r"[._]+", " ", title).strip(" -_[]【】()（）")
        return title, year

    def _media_matches(self, media: dict[str, Any], target: dict[str, Any]) -> bool:
        expected_ids = {
            str(key).casefold(): str(value)
            for key, value in (target.get("external_ids") or {}).items()
            if str(key).strip() and str(value).strip()
        }
        actual_ids = {
            str(key).casefold(): str(value)
            for key, value in (media.get("provider_ids") or {}).items()
            if str(key).strip() and str(value).strip()
        }
        if any(actual_ids.get(key) == value for key, value in expected_ids.items()):
            return True
        expected_title = self._key(target.get("title"))
        if not expected_title:
            return False
        titles = {
            self._key(media.get("name")),
            self._key(media.get("original_title")),
        }
        if expected_title not in titles:
            return False
        expected_year = str(target.get("year") or "")[:4]
        actual_year = str(media.get("year") or "")[:4]
        return not expected_year or not actual_year or expected_year == actual_year

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
        *,
        targets: list[dict[str, Any]] | None = None,
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
                await self._process_library(context, state, server_id, library_id, targets=targets)

    async def _process_library(
        self,
        context: PluginContext,
        state: _RunState,
        server_id: str,
        library_id: str,
        *,
        targets: list[dict[str, Any]] | None = None,
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
            selected = [
                item
                for item in items
                if not targets or any(self._media_matches(item, target) for target in targets)
            ]
            for offset in range(0, len(selected), 2):
                pending = []
                async with asyncio.TaskGroup() as tasks:
                    for item in selected[offset : offset + 2]:
                        pending.append(
                            tasks.create_task(
                                process_checkpoint(self, context, state, server_id, item)
                            )
                        )
                if any(task.cancelled() for task in pending):
                    raise asyncio.CancelledError()
            start += len(items)
            if not items or start >= int(page.get("total") or 0):
                return

    async def _process_media(self, context, state, server_id, media):
        state.scanned_media += 1
        people = list(media.get("people") or [])
        original_people = people
        previous_failures = state.failures
        needs_roles = any(
            self._want_role(context, p)
            and not self._has_han(p.get("Role"))
            and str(p.get("Type") or "").casefold() == "actor"
            for p in people
        )
        roles = await self._localized_roles(context, media, state) if needs_roles else {}
        cast = state.casts.get(self._media_key(media), [])
        role_people = [self._role_only(context, state, p, cast, roles) for p in people]
        if role_people != people and await self._write_people(
            context, state, server_id, media, people, role_people
        ):
            people = role_people
        updated_people = []
        for person in people:
            state.scanned_people += 1
            updated = await self._process_person(
                context, state, server_id, media, person, roles, cast
            )
            if updated is not None:
                updated_people.append(updated)
        if updated_people != people:
            if await self._write_people(context, state, server_id, media, people, updated_people):
                people = updated_people
        if state.failures == previous_failures and len(original_people) == len(people):
            state.skipped_people += sum(
                before == after
                and f"{server_id}:{after.get('Id') or ''}" not in state.changed_people
                for before, after in zip(original_people, people)
            )
        return self._media_role_outcome(context, original_people, people)

    def _media_role_outcome(self, context, original_people, people):
        remaining = sum(
            str(p.get("Type") or "").casefold() == "actor"
            and self._want_role(context, p)
            and not self._has_han(p.get("Role"))
            for p in people
        )
        changed_roles = role_changes(original_people, people)
        return {
            "status": "partial" if remaining else "completed",
            "updated_roles": changed_roles,
            "remaining_roles": remaining,
            "message": (
                f"中文角色更新 {changed_roles}，仍有 {remaining} 个角色未中文化（来源缺失或无法匹配）"
                if remaining
                else f"中文角色更新 {changed_roles}，角色检查通过"
            ),
        }

    async def _write_people(self, context, state, server_id, media, previous, updated):
        if not media.get("id"):
            return False
        try:
            await context.media_servers.update_item_metadata(
                server_id, str(media["id"]), {"People": updated}
            )
        except Exception as error:
            state.failures += 1
            state.retry_media.add(str(media.get("id")))
            context.logger.warning(
                "媒体人物列表写入失败：%s / %s", media.get("name"), type(error).__name__
            )
            return False
        state.updated_roles += role_changes(previous, updated)
        state.removed_people += max(0, len(previous) - len(updated))
        key = f"{server_id}:{media['id']}"
        if key not in state.media_written:
            state.media_written.add(key)
            state.updated_media += 1
        return True

    async def _process_person(
        self,
        context: PluginContext,
        state: _RunState,
        server_id: str,
        media: dict[str, Any],
        person: dict[str, Any],
        localized_roles: dict[str, str],
        cast: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        eligible = self._want_name(context, person)
        if not eligible and not person.get("Id"):
            return person
        key = f"{server_id}:{person.get('Id') or self._key(person.get('Name'))}"
        async with state.person_locks.setdefault(key, asyncio.Lock()):
            profile = await self._profile(context, state, server_id, person, cast, media)
            localized_name = self._localized_name(profile) if eligible else ""
            await self._update_profile_item(
                context, state, server_id, person, profile, localized_name
            )
        identity_person = {
            **person,
            "ProviderIds": profile.get("_provider_ids") or person.get("ProviderIds") or {},
        }
        matched = self._role_only(context, state, identity_person, cast, localized_roles)
        localized_role = self._localized_role(
            profile,
            media,
            localized_roles,
            person_name=str(person.get("Name") or ""),
            person_role=str(person.get("Role") or ""),
            localized_name=localized_name,
        )
        if matched.get("Role") != person.get("Role"):
            localized_role = str(matched["Role"])
        elif self._identity_cast(identity_person, cast) or not self._want_role(context, person):
            localized_role = ""
        self._record_role_gap(
            context, state, media, identity_person, cast, localized_role, localized_name
        )
        if not localized_name and not localized_role:
            return (
                None if can_remove(self, context, state, media, person, profile, cast) else person
            )
        updated = dict(person)
        if localized_name:
            updated["Name"] = localized_name
        if localized_role and not self._has_han(person.get("Role")):
            updated["Role"] = localized_role
        return updated

    def _want_name(self, context: Any, person: dict) -> bool:
        return str(context.config.get("condition") or "missing_any") != "missing_role"

    def _want_role(self, context: Any, person: dict) -> bool:
        return str(
            context.config.get("condition") or "missing_any"
        ) != "missing_name" and self._eligible(context, person)

    def _role_only(
        self, context: Any, state: _RunState, person: dict, cast: list, roles: dict
    ) -> dict:
        if (
            not self._want_role(context, person)
            or self._has_han(person.get("Role"))
            or str(person.get("Type", "")).casefold() != "actor"
        ):
            return person
        matched = self._identity_cast(person, cast)
        if not matched:
            matched = [
                row for row in cast if self._person_matches(str(person.get("Name") or ""), row)
            ]
        candidates = {str(row.get("character") or row.get("role") or "") for row in matched}
        candidates = {role for role in candidates if self._is_chinese_role(role)}
        role = next(iter(candidates)) if len(candidates) == 1 else ""
        if not role and not matched:
            role = roles.get("role:" + self._latin_role_key(person.get("Role")), "")
        if role:
            return {**person, "Role": role[:256]}
        return person

    @staticmethod
    def _identity_cast(person, cast):
        ids = {str(k).casefold(): str(v) for k, v in (person.get("ProviderIds") or {}).items()}
        return [
            row
            for row in cast
            if row.get("source_id")
            and ids.get(str(row.get("source_key") or "").casefold()) == str(row["source_id"])
        ]

    def _record_role_gap(self, context, state, media, person, cast, role, name):
        if role or self._has_han(person.get("Role")) or not self._want_role(context, person):
            return
        if (
            str(person.get("Type") or "").casefold() != "actor"
            or str(media.get("id")) in state.retry_media
        ):
            return
        matched = bool(self._identity_cast(person, cast)) or any(
            self._person_matches(str(person.get("Name") or ""), row)
            or self._person_matches(name, row)
            for row in cast
        )
        state.no_chinese_role += int(matched)
        state.unmatched_people += int(not matched)

    async def _localized_roles(
        self,
        context: PluginContext,
        media: dict[str, Any],
        state: _RunState | None = None,
    ) -> dict[str, str]:
        key = self._media_key(media)
        if state is not None and key in state.casts:
            return self._role_map(state.casts[key])
        failures = state.request_failures if state is not None else 0
        cast = await self._read_cast(context, media)
        if state is not None:
            if state.request_failures > failures:
                state.retry_media.add(str(media.get("id")))
            state.casts[key] = cast
        return self._role_map(cast)

    @staticmethod
    def _media_key(media: dict[str, Any]) -> str:
        ids = sorted(dict(media.get("provider_ids") or {}).items())
        return repr(
            (
                media.get("media_type") or media.get("type"),
                ids,
                media.get("name"),
                media.get("year"),
            )
        )

    async def _read_cast(
        self, context: PluginContext, media: dict[str, Any]
    ) -> list[dict[str, Any]]:
        item_type = str(media.get("media_type") or media.get("type") or "").casefold()
        media_type = "tv" if item_type == "series" else "movie"
        provider_ids = {
            str(key).casefold(): str(value)
            for key, value in dict(media.get("provider_ids") or {}).items()
            if str(value).strip()
        }
        source_id = provider_ids.get("douban") or provider_ids.get("doubanid") or ""
        try:
            if not source_id:
                identity = await context.media.search_source_identity(
                    source="douban",
                    title=str(media.get("name") or media.get("original_title") or ""),
                    media_type=media_type,
                    year=str(media.get("year") or "")[:4],
                )
                if not identity:
                    return []
                if (
                    str(identity.get("source_key") or identity.get("source") or "").casefold()
                    != "douban"
                ):
                    context.logger.warning("角色来源不匹配，已跳过：%s", media.get("name"))
                    return []
                source_id = str(identity.get("source_id") or "")
            if not source_id:
                return []
            detail = await context.media.detail(
                "douban",
                {
                    "source_id": source_id,
                    "include_recommendations": False,
                    "include_library": False,
                    "title": str(media.get("name") or ""),
                    "original_title": str(media.get("original_title") or ""),
                    "media_type": media_type,
                    "year": str(media.get("year") or "")[:4],
                },
            )
        except Exception as error:
            context.logger.warning(
                "豆瓣角色信息读取失败：%s / %s", media.get("name"), type(error).__name__
            )
            return []
        return self._cast_rows(detail)

    @staticmethod
    def _cast_rows(detail):
        return [
            row for row in detail.get("cast") or detail.get("actors") or [] if isinstance(row, dict)
        ] + [
            {key: value for key, value in row.items() if key not in {"character", "role"}}
            for group in ("directors", "writers", "crew")
            for row in detail.get(group) or []
            if isinstance(row, dict)
        ]

    def _role_map(self, cast: list[dict[str, Any]]) -> dict[str, str]:
        roles: dict[str, str] = {}
        ambiguous_role_keys: set[str] = set()
        for person in cast:
            if not isinstance(person, dict):
                continue
            role = str(person.get("character") or person.get("role") or "").strip()
            if not self._is_chinese_role(role):
                continue
            names = [
                person.get("name"),
                person.get("title"),
                *self._strings(person.get("aliases")),
                *self._strings(person.get("also_known_as")),
            ]
            for name in names:
                key = self._key(name)
                if key:
                    self._insert_unique_role(roles, ambiguous_role_keys, key, role[:256])
            role_key = self._latin_role_key(role)
            if role_key:
                lookup_key = f"role:{role_key}"
                existing = roles.get(lookup_key)
                if existing and existing != role:
                    ambiguous_role_keys.add(lookup_key)
                elif lookup_key not in ambiguous_role_keys:
                    roles[lookup_key] = role[:256]
        for key in ambiguous_role_keys:
            roles.pop(key, None)
        return roles

    @staticmethod
    def _insert_unique_role(roles, ambiguous, key, role):
        if key in roles and roles[key] != role:
            ambiguous.add(key)
        elif key not in ambiguous:
            roles[key] = role

    async def _profile(
        self,
        context: PluginContext,
        state: _RunState,
        server_id: str,
        person: dict[str, Any],
        cast: list[dict[str, Any]],
        media: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = f"{server_id}:{person.get('Id') or self._key(person.get('Name'))}"
        if key in state.profiles:
            return state.profiles[key]
        metadata: dict[str, Any] = {}
        if person.get("Id"):
            try:
                metadata = await context.media_servers.item_metadata(server_id, str(person["Id"]))
            except Exception as error:
                state.failures += 1
                if media is not None:
                    state.retry_media.add(str(media.get("id")))
                context.logger.debug("人物现有资料读取失败：%s - %s", person.get("Name"), error)
                return {"_lookup_complete": False}
            if not metadata:
                return {"_lookup_complete": False}
        profile = await self._resolve_sources(context, person, metadata, cast, state, media)
        state.profiles[key] = profile
        return profile

    async def _resolve_sources(
        self,
        context: PluginContext,
        person: dict[str, Any],
        metadata: dict[str, Any],
        cast: list[dict[str, Any]],
        state: _RunState | None = None,
        media: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        name = str(person.get("Name") or metadata.get("name") or "").strip()
        existing = self._existing_profile(person, metadata, name)
        merged = dict(existing)
        lookup_complete = True
        include_name = self._want_name(context, person)
        checked, source_matched = set(), False
        for source in ("tmdb", "douban"):
            if not self._missing_fields(context, merged, include_name=include_name):
                break
            try:
                actor: dict[str, Any] = {}
                if source == "douban":
                    actor = await self._matching_cast(context, name, merged, cast, state, media)
                    source_matched = source_matched or bool(actor)
                    merged = self._merge_profiles([merged, actor])
                    if not self._missing_fields(context, merged, include_name=include_name):
                        break
                payload = await self._actor_payload(context, source, name, metadata, actor)
                if not payload:
                    # Skipping a name search is not evidence that the person
                    # does not exist; do not authorize unresolved removal.
                    lookup_complete = False
                    continue
                source_matched = True
                if source == "douban":
                    payload = {**payload, "include_fallback": False}
                merged = self._merge_profiles(
                    [merged, await context.media.person_detail(source, payload)]
                )
                checked.add(source)
            except Exception as error:
                lookup_complete = False
                if state is not None and media is not None:
                    state.retry_media.add(str(media.get("id")))
                context.logger.debug("人物来源查询失败：%s / %s - %s", name, source, error)
        return annotate_profile(
            merged, existing, metadata, lookup_complete, checked, source_matched
        )

    async def _actor_payload(self, context, source, name, metadata, actor):
        actor_id = actor.get("douban_person_id") or actor.get("source_id")
        if actor_id:
            return {"source_key": source, "source_id": str(actor_id), "name": name}
        return await self._source_payload(context, source, name, metadata)

    @staticmethod
    def _existing_profile(person, metadata, name):
        return {
            "name": metadata.get("name") or name,
            "biography": metadata.get("overview") or "",
            "profile": bool(metadata.get("has_primary_image") or person.get("PrimaryImageTag")),
        }

    async def _matching_cast(self, context, name, merged, cast, state, media):
        if state is not None and media is not None:
            key = self._media_key(media)
            if key not in state.casts:
                state.casts[key] = await self._read_cast(context, media)
            cast = state.casts[key]
        return next(
            (
                row
                for row in cast
                if self._person_matches(name, row)
                or self._person_matches(self._localized_name(merged), row)
            ),
            {},
        )

    def _missing_fields(
        self, context: PluginContext, profile: dict[str, Any], *, include_name: bool = True
    ) -> set[str]:
        missing = set()
        if include_name and not self._localized_name(profile):
            missing.add("name")
        if context.config.get("update_biography", True) and not self._has_han(
            profile.get("biography")
        ):
            missing.add("biography")
        if not (profile.get("profile") or profile.get("poster")):
            missing.add("profile")
        return missing

    async def _source_payload(
        self,
        context: PluginContext,
        source: str,
        name: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        provider_ids = {
            str(k).casefold(): v for k, v in dict(metadata.get("provider_ids") or {}).items()
        }
        direct_id = str(provider_ids.get(source) or "")
        if direct_id:
            return {"source_key": source, "source_id": direct_id, "name": name}
        # Only use known person IDs or the work's cast; never search by name.
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
        key = f"{server_id}:{person_id}"
        if not person_id or key in state.updated_people or "_existing" not in profile:
            return
        changes = self._profile_changes(context, profile, localized_name)
        try:
            if changes:
                await context.media_servers.update_item_metadata(server_id, person_id, changes)
                state.changed_people.add(key)
                state.updated_profiles += 1
                state.updated_names += int("Name" in changes)
                state.updated_biographies += int("Overview" in changes)
            if not profile["_existing"].get("profile"):
                await self._update_profile_image(context, state, server_id, person_id, profile)
            state.updated_people.add(key)
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
        content_type = self._image_content_type(content)
        if content_type == "image/webp":
            content = await asyncio.to_thread(self._webp_to_png, content)
            content_type = "image/png"
        await context.media_servers.set_primary_image(
            server_id,
            person_id,
            content,
            content_type=content_type,
        )
        state.updated_images += 1
        state.changed_people.add(f"{server_id}:{person_id}")

    @staticmethod
    def _webp_to_png(content: bytes) -> bytes:
        from PIL import Image

        with Image.open(BytesIO(content)) as image:
            image.seek(0)
            output = BytesIO()
            image.convert("RGBA" if "A" in image.getbands() else "RGB").save(output, "PNG")
            return output.getvalue()

    @staticmethod
    def _image_content_type(content: bytes) -> str:
        if content.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            return "image/webp"
        raise ValueError("人物图片格式不受支持")

    def _profile_changes(
        self,
        context: PluginContext,
        profile: dict[str, Any],
        localized_name: str,
    ) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        existing = profile.get("_existing") or {}
        locked = [str(value) for value in profile.get("_locked_fields") or [] if value]
        if localized_name and not self._has_han(existing.get("name")):
            changes["Name"] = localized_name
            if "Name" not in locked:
                locked.append("Name")
        biography = str(profile.get("biography") or "").strip()
        if (
            context.config.get("update_biography", True)
            and self._has_han(biography)
            and not self._has_han(existing.get("biography"))
        ):
            changes["Overview"] = biography
            if "Overview" not in locked:
                locked.append("Overview")
        if changes and locked:
            changes["LockedFields"] = locked
        return changes

    def _merge_profiles(self, profiles: list[dict[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        aliases: list[str] = []
        works: list[dict[str, Any]] = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            for key, value in profile.items():
                if (
                    key in {"name", "biography"}
                    and self._has_han(value)
                    and not self._has_han(merged.get(key))
                ):
                    merged[key] = value
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
        values = [
            profile.get("name"),
            profile.get("title"),
            *(profile.get("also_known_as") or []),
        ]
        for value in values:
            if self._has_han(value):
                return str(value).strip()[:256]
        return ""

    def _localized_role(
        self,
        profile: dict[str, Any],
        media: dict[str, Any],
        localized_roles: dict[str, str],
        *,
        person_name: str,
        person_role: str,
        localized_name: str,
    ) -> str:
        names = [
            person_name,
            localized_name,
            profile.get("name"),
            profile.get("title"),
            *self._strings(profile.get("also_known_as")),
        ]
        for name in names:
            role = localized_roles.get(self._key(name), "")
            if role:
                return role
        role_key = self._latin_role_key(person_role)
        if role_key:
            role = localized_roles.get(f"role:{role_key}", "")
            if role:
                return role
        provider_ids = {
            str(key).casefold(): str(value)
            for key, value in dict(media.get("provider_ids") or {}).items()
        }
        media_names = {
            self._key(media.get("name")),
            self._key(media.get("original_title")),
        } - {""}
        for work in profile.get("works") or []:
            work_id = str(
                work.get("source_id") or work.get("tmdb_id") or work.get("media_id") or ""
            )
            work_names = {self._key(work.get("title")), self._key(work.get("name"))} - {""}
            matches_id = work_id and work_id in set(provider_ids.values())
            if not matches_id and not media_names.intersection(work_names):
                continue
            role = str(work.get("character") or work.get("role") or "").strip()
            if self._is_chinese_role(role):
                return role[:256]
        return ""

    def _person_matches(self, expected: str, item: dict[str, Any]) -> bool:
        names = [
            item.get("name"),
            item.get("title"),
            *(item.get("also_known_as") or []),
            *(item.get("aliases") or []),
        ]
        expected_key = self._key(expected)
        return bool(expected_key and expected_key in {self._key(value) for value in names})

    @classmethod
    def _is_chinese_role(cls, value: object) -> bool:
        role = str(value or "").strip()
        # Credit sources also put occupation labels in the character field.
        parts = re.split(r"\s*[/、,，]\s*", role)
        occupations = {"演员", "配音", "配音演员", "主演", "参演", "出演", "客串"}
        return cls._has_han(role) and not all(part in occupations for part in parts)

    @staticmethod
    def _has_han(value: object) -> bool:
        return bool(_HAN.search(str(value or "")))

    @staticmethod
    def _key(value: object) -> str:
        return _SPACE.sub("", str(value or "")).casefold()

    @staticmethod
    def _latin_role_key(value: object) -> str:
        without_han = _HAN.sub("", str(value or "")).casefold()
        return re.sub(r"[^a-z0-9]+", "", without_han)

    @staticmethod
    def _strings(value: object) -> list[str]:
        values = value if isinstance(value, (list, tuple, set)) else []
        return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))
