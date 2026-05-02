from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth_routes import current_user
from app.services.auth_service import User
from app.services.entitlements import get_entitlement_status


router = APIRouter(prefix="/api/entitlements", tags=["entitlements"])


@router.get("/status")
def status(user: User = Depends(current_user)) -> dict:
    return get_entitlement_status(user)
