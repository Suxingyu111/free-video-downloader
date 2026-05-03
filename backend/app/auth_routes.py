from __future__ import annotations

import hashlib
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.services.app_config import load_config
from app.services.auth_service import (
    User,
    authenticate_user,
    create_password_reset_token,
    create_session,
    create_user,
    get_user_by_session_token,
    reset_password,
    rotate_session_csrf_token,
    revoke_session,
    verify_session_csrf_token,
)
from app.services.client_ip import client_ip_from_request
from app.services.billing_service import get_membership
from app.services.csrf import (
    assert_same_origin,
    create_prelogin_csrf_token,
    csrf_header,
    verify_prelogin_csrf_token,
)
from app.services.entitlements import get_usage_summary
from app.services.rate_limit import (
    RateLimitExceeded,
    assert_rate_limit_allowed,
    clear_rate_limit,
    record_rate_limit_hit,
)


router = APIRouter(prefix="/api", tags=["auth"])


class AuthRequest(BaseModel):
    email: str
    password: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    password: str


def _client_ip(request: Request) -> str:
    return client_ip_from_request(request)


def _rate_limit_keys(action: str, request: Request, email: str) -> list[str]:
    normalized = email.strip().lower()
    return [f"auth:{action}:ip:{_client_ip(request)}", f"auth:{action}:email:{normalized}"]


def _password_reset_confirm_rate_limit_keys(request: Request, token: str) -> list[str]:
    ip = _client_ip(request)
    token_hash_prefix = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return [
        f"auth:password-reset-confirm:ip:{ip}",
        f"auth:password-reset-confirm:ip-token:{ip}:{token_hash_prefix}",
    ]


def _assert_auth_rate_limit(action: str, request: Request, email: str) -> list[str]:
    config = load_config()
    keys = _rate_limit_keys(action, request, email)
    try:
        for key in keys:
            assert_rate_limit_allowed(
                key,
                limit=config.auth_rate_limit_attempts,
                window_seconds=config.auth_rate_limit_window_seconds,
            )
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return keys


def _record_auth_rate_limit(keys: list[str]) -> None:
    config = load_config()
    for key in keys:
        record_rate_limit_hit(key, window_seconds=config.auth_rate_limit_window_seconds)


def _clear_auth_rate_limit(keys: list[str]) -> None:
    for key in keys:
        clear_rate_limit(key)


def _set_session_cookie(response: Response, token: str) -> None:
    config = load_config()
    response.set_cookie(
        config.session_cookie_name,
        token,
        httponly=True,
        samesite="lax",
        secure=config.secure_cookies,
        max_age=config.session_days * 86400,
        path="/",
    )


def current_user(request: Request) -> User:
    config = load_config()
    user = get_user_by_session_token(request.cookies.get(config.session_cookie_name))
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def optional_user(request: Request) -> User | None:
    config = load_config()
    return get_user_by_session_token(request.cookies.get(config.session_cookie_name))


def _assert_prelogin_csrf(request: Request) -> None:
    assert_same_origin(request)
    verify_prelogin_csrf_token(csrf_header(request))


def _assert_session_csrf(request: Request) -> None:
    assert_same_origin(request)
    config = load_config()
    if not verify_session_csrf_token(
        request.cookies.get(config.session_cookie_name),
        csrf_header(request),
    ):
        raise HTTPException(status_code=403, detail="CSRF token 无效")


def _me_payload(user: User, csrf_token: str | None = None) -> dict:
    membership = get_membership(user.id)
    usage = get_usage_summary(user)
    payload = {
        "user": user.as_dict(),
        "membership": membership.as_dict(),
        "usage": usage.as_dict(),
    }
    if csrf_token:
        payload["csrf_token"] = csrf_token
    return payload


@router.get("/csrf")
def csrf() -> dict[str, str]:
    return {"csrf_token": create_prelogin_csrf_token()}


@router.post("/auth/register")
def register(payload: AuthRequest, request: Request, response: Response) -> dict:
    _assert_prelogin_csrf(request)
    keys = _assert_auth_rate_limit("register", request, payload.email)
    _record_auth_rate_limit(keys)
    try:
        user = create_user(payload.email, payload.password)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400, detail="邮箱已被注册") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="注册失败") from exc
    session = create_session(
        user.id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, session.session_token)
    return _me_payload(user, session.csrf_token)


@router.post("/auth/login")
def login(payload: AuthRequest, request: Request, response: Response) -> dict:
    _assert_prelogin_csrf(request)
    keys = _assert_auth_rate_limit("login", request, payload.email)
    user = authenticate_user(payload.email, payload.password)
    if user is None:
        _record_auth_rate_limit(keys)
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    _clear_auth_rate_limit(keys)
    session = create_session(
        user.id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, session.session_token)
    return _me_payload(user, session.csrf_token)


@router.post("/auth/logout")
def logout(request: Request, response: Response, _: User = Depends(current_user)) -> dict[str, bool]:
    config = load_config()
    _assert_session_csrf(request)
    revoke_session(request.cookies.get(config.session_cookie_name), reason="logout")
    response.delete_cookie(config.session_cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request, user: User = Depends(current_user)) -> dict:
    config = load_config()
    csrf_token = rotate_session_csrf_token(request.cookies.get(config.session_cookie_name))
    return _me_payload(user, csrf_token)


@router.post("/auth/password-reset/request")
def request_password_reset(payload: PasswordResetRequest, request: Request) -> dict:
    _assert_prelogin_csrf(request)
    keys = _assert_auth_rate_limit("password-reset", request, payload.email)
    _record_auth_rate_limit(keys)
    token = create_password_reset_token(payload.email)
    response = {"ok": True}
    if token and load_config().dev_mode:
        response["reset_token"] = token
    return response


@router.post("/auth/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirm, request: Request) -> dict[str, bool]:
    _assert_prelogin_csrf(request)
    token = payload.token.strip()
    keys = _password_reset_confirm_rate_limit_keys(request, token)
    config = load_config()
    try:
        for key in keys:
            assert_rate_limit_allowed(
                key,
                limit=config.auth_rate_limit_attempts,
                window_seconds=config.auth_rate_limit_window_seconds,
            )
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    try:
        changed = reset_password(token, payload.password)
    except ValueError as exc:
        _record_auth_rate_limit(keys)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not changed:
        _record_auth_rate_limit(keys)
        raise HTTPException(status_code=400, detail="重置链接无效或已过期")
    _clear_auth_rate_limit(keys[1:])
    return {"ok": True}
