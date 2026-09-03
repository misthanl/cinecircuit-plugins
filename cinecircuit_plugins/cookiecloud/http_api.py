import gzip
import hmac
import io
import json
from urllib.parse import parse_qs

from fastapi import HTTPException

from app.modules.plugins.contracts import PluginApiRequest, PluginContext, PluginHttpResponse
from .crypto import SUPPORTED_CRYPTO_TYPES
from .snapshot import load_snapshot, store_snapshot

MAX_UPLOAD_BYTES = 9 * 1024 * 1024
CORS_HEADERS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "GET,POST,OPTIONS"}


def _upload_payload(body: bytes) -> dict[str, object]:
    if not body or len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413 if body else 400, detail="CookieCloud 上传大小无效")
    if body[:2] == b"\x1f\x8b":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
                body = stream.read(MAX_UPLOAD_BYTES + 1)
        except (OSError, EOFError) as error:
            raise HTTPException(status_code=400, detail="CookieCloud 压缩数据无效") from error
        if len(body) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="CookieCloud 上传过大")
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        try:
            parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
            value = {key: values[-1] for key, values in parsed.items() if values}
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=400, detail="CookieCloud 上传格式无效") from error
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="CookieCloud 上传格式无效")
    return value


def _check_key(config: dict, uuid: str) -> None:
    configured = str(config.get("user_key") or "").strip()
    if not configured or not uuid or not hmac.compare_digest(configured, uuid):
        raise HTTPException(status_code=404, detail="CookieCloud 服务未配置")


async def handle(request: PluginApiRequest, context: PluginContext) -> PluginHttpResponse:
    if request.method == "OPTIONS":
        return PluginHttpResponse({}, headers=CORS_HEADERS)
    if request.action == "health" and request.method == "GET":
        return PluginHttpResponse({"status": "OK"}, headers=CORS_HEADERS)
    if request.action == "update" and request.method == "POST":
        payload = _upload_payload(request.content)
        uuid = str(payload.get("uuid") or "").strip()
        _check_key(context.config, uuid)
        encrypted = str(payload.get("encrypted") or "").strip()
        crypto_type = str(payload.get("crypto_type") or "legacy").strip().casefold()
        if not encrypted or crypto_type not in SUPPORTED_CRYPTO_TYPES:
            raise HTTPException(status_code=400, detail="CookieCloud 上传数据无效")
        store_snapshot(context.state, uuid=uuid, encrypted=encrypted, crypto_type=crypto_type)
        return PluginHttpResponse({"action": "done"}, headers=CORS_HEADERS)
    if request.action.startswith("get/") and request.method in {"GET", "POST"}:
        uuid = request.action.removeprefix("get/").strip()
        _check_key(context.config, uuid)
        snapshot = load_snapshot(context.state, uuid=uuid)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="CookieCloud 快照不存在")
        return PluginHttpResponse({"encrypted": snapshot["encrypted"], "crypto_type": snapshot["crypto_type"]}, headers=CORS_HEADERS)
    raise KeyError("CookieCloud 接口不存在")
