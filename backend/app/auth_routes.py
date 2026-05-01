from __future__ import annotations

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
    revoke_session,
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


def _me_payload(user: User) -> dict:
    return {
        "user": user.as_dict(),
        "membership": {"plan": "free", "status": "free", "active": False},
        "usage": {
            "daily_free_limit": load_config().free_summary_daily_limit,
            "used_today": 0,
            "remaining_today": load_config().free_summary_daily_limit,
        },
    }


@router.post("/auth/register")
def register(payload: AuthRequest, response: Response) -> dict:
    try:
        user = create_user(payload.email, payload.password)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _set_session_cookie(response, create_session(user.id))
    return _me_payload(user)


@router.post("/auth/login")
def login(payload: AuthRequest, response: Response) -> dict:
    user = authenticate_user(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    _set_session_cookie(response, create_session(user.id))
    return _me_payload(user)


@router.post("/auth/logout")
def logout(request: Request, response: Response, _: User = Depends(current_user)) -> dict[str, bool]:
    config = load_config()
    revoke_session(request.cookies.get(config.session_cookie_name))
    response.delete_cookie(config.session_cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return _me_payload(user)


@router.post("/auth/password-reset/request")
def request_password_reset(payload: PasswordResetRequest) -> dict:
    token = create_password_reset_token(payload.email)
    response = {"ok": True}
    if token:
        response["reset_token"] = token
    return response


@router.post("/auth/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirm) -> dict[str, bool]:
    try:
        changed = reset_password(payload.token, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=400, detail="重置链接无效或已过期")
    return {"ok": True}
