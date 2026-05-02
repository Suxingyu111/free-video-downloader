from __future__ import annotations

import base64
import hmac
import json
import secrets
from hashlib import sha256
from time import time
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from app.services.app_config import load_config


PRELOGIN_TTL_SECONDS = 30 * 60
CSRF_HEADER_NAME = "x-csrf-token"
_PRELOGIN_PURPOSE = "prelogin"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _signing_key() -> bytes:
    return load_config().ip_hash_salt.encode("utf-8")


def _origin(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def allowed_origins() -> set[str]:
    config = load_config()
    origins = {_origin(origin) for origin in config.allowed_origins}
    origins.add(_origin(config.public_app_url))
    origins.discard("")
    return origins


def csrf_header(request: Request) -> str | None:
    return request.headers.get(CSRF_HEADER_NAME)


def create_prelogin_csrf_token() -> str:
    payload = {
        "purpose": _PRELOGIN_PURPOSE,
        "iat": time(),
        "nonce": secrets.token_urlsafe(16),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_part = _b64encode(payload_bytes)
    signature = hmac.new(_signing_key(), payload_part.encode("ascii"), sha256).digest()
    return f"{payload_part}.{_b64encode(signature)}"


def verify_prelogin_csrf_token(token: str | None) -> None:
    if not token:
        raise HTTPException(status_code=403, detail="CSRF token 无效")
    try:
        payload_part, signature_part = token.split(".", 1)
        expected = hmac.new(_signing_key(), payload_part.encode("ascii"), sha256).digest()
        provided = _b64decode(signature_part)
        payload = json.loads(_b64decode(payload_part))
    except Exception as exc:
        raise HTTPException(status_code=403, detail="CSRF token 无效") from exc
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=403, detail="CSRF token 无效")
    if payload.get("purpose") != _PRELOGIN_PURPOSE:
        raise HTTPException(status_code=403, detail="CSRF token 无效")
    issued_at = payload.get("iat")
    if not isinstance(issued_at, (int, float)) or time() - issued_at > PRELOGIN_TTL_SECONDS:
        raise HTTPException(status_code=403, detail="CSRF token 已过期")


def create_session_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def assert_same_origin(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origins = allowed_origins()
    origin = request.headers.get("origin")
    if origin:
        if _origin(origin) not in origins:
            raise HTTPException(status_code=403, detail="请求来源不被允许")
        return
    referer = request.headers.get("referer")
    if not referer or _origin(referer) not in origins:
        raise HTTPException(status_code=403, detail="请求来源不被允许")
