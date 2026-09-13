"""Cover history, preview and library-selection page operations."""

import asyncio
import json


class CoverApi:
    def __init__(self, plugin):
        self.plugin = plugin

    async def _history_api(self, request, context):
        from .history import CoverHistory, MIMES, packed

        history = CoverHistory()
        if request.action == "history" and request.method == "GET":
            await asyncio.to_thread(history.import_latest, context.items.list(500), context.config)
            result = await asyncio.to_thread(history.listing, context.config)
            servers = await context.media_servers.configurations()
            names = {x["id"]: x["name"] for x in servers.get("items", [])}
            for row in result["items"]:
                row["server_name"] = names.get(row["server_id"], row["server_id"])
            return result
        if request.action == "history_image" and request.method == "GET":
            thumb = request.query.get("thumbnail") == "1"
            row, data = await asyncio.to_thread(history.read, request.query.get("id", ""), thumb)
            return packed(data, "image/jpeg" if thumb else MIMES[row["suffix"]])
        if request.action == "history_delete" and request.method == "POST":
            return await asyncio.to_thread(history.delete, request.payload.get("ids"))
        if request.action == "history_apply" and request.method == "POST":
            return await self._apply_history(request, context, history)
        raise ValueError("历史封面请求方式不正确")

    async def _targets_api(self, request, context):
        configurations = await context.media_servers.configurations()
        servers = [
            item
            for item in configurations.get("items", [])
            if item.get("enabled", True)
            and str(item.get("type", "")).casefold() in {"emby", "jellyfin"}
        ]
        requested = json.loads(request.query.get("servers", "[]"))
        if not isinstance(requested, list) or len(requested) > 100:
            raise ValueError("媒体服务器选择无效")
        wanted = set(map(str, requested))
        libraries: list[dict[str, str]] = []
        errors = []
        for server in servers:
            if server["id"] not in wanted:
                continue
            try:
                result = await context.media_servers.libraries(server["id"])
                libraries.extend(
                    {
                        "value": json.dumps(
                            [server["id"], str(item["id"])],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        "title": f"{server['name']}：{item['name']}",
                    }
                    for item in result.get("items", [])
                )
            except Exception:
                errors.append(f"{server['name']}：媒体库读取失败，请检查连接后重试")
        return {
            "servers": [{"value": item["id"], "title": item["name"]} for item in servers],
            "libraries": libraries,
            "errors": errors,
        }

    async def _inventory_api(self, request, context):
        servers = await context.media_servers.configurations()
        selected = self.plugin._string_set(context.config.get("selected_servers"))
        server_id = next(iter(selected), str(servers.get("active_id") or ""))
        libraries = await context.media_servers.libraries(server_id) if server_id else {"items": []}
        return {
            "servers": servers.get("items", []),
            "libraries": libraries.get("items", []),
            "config": context.config,
            "history": context.items.list(100),
        }

    async def _preview_api(self, request, context):
        from .preview import render_preview, start_preview

        config = request.payload.get("config", {})
        if not isinstance(config, dict):
            raise ValueError("预览设置格式不正确")
        font_path = await self.plugin._ensure_cjk_font(context)
        if request.payload.get("async"):
            return start_preview(self.plugin, {**context.config, **config}, font_path)
        return await render_preview(self.plugin, {**context.config, **config}, font_path)

    async def _apply_history(self, request, context, history):
        from .history import MIMES

        row, data = await asyncio.to_thread(history.read, request.payload.get("id", ""))
        servers = await context.media_servers.configurations()
        if not any(
            x["id"] == row["server_id"]
            and x.get("enabled")
            and x.get("type") in {"emby", "jellyfin"}
            for x in servers.get("items", [])
        ):
            raise ValueError("媒体服务器已停用或删除")
        libraries = await context.media_servers.libraries(row["server_id"])
        if not any(str(x["id"]) == row["library_id"] for x in libraries.get("items", [])):
            raise ValueError("媒体库已删除")
        await context.media_servers.set_primary_image(
            row["server_id"], row["library_id"], data, content_type=MIMES[row["suffix"]]
        )
        context.items.record(
            f"emby-cover:{row['server_id']}:{row['library_id']}",
            "updated",
            payload={"server_id": row["server_id"], "library_id": row["library_id"]},
            result={**row, "status": "updated"},
        )
        await asyncio.to_thread(history.applied, row["id"])
        return {"applied": True}
