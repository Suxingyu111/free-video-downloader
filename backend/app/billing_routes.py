from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth_routes import current_user
from app.services.app_config import load_config
from app.services.auth_service import User
from app.services.billing_service import (
    activate_mock_subscription,
    cancel_mock_subscription,
    create_mock_checkout,
    expire_mock_subscription,
    fail_mock_payment,
    get_membership,
)


router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/status")
def billing_status(user: User = Depends(current_user)) -> dict:
    return {"membership": get_membership(user.id).as_dict(), "mode": load_config().billing_mode}


@router.post("/checkout")
def billing_checkout(user: User = Depends(current_user)) -> dict:
    config = load_config()
    membership = get_membership(user.id)
    if membership.active:
        raise HTTPException(status_code=409, detail="你已经是专业版会员，请前往会员管理。")
    if config.billing_mode == "mock":
        return create_mock_checkout(user)
    raise HTTPException(status_code=503, detail="Stripe 支付尚未配置")


@router.post("/mock/activate")
def mock_activate(user: User = Depends(current_user)) -> dict:
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    return {"membership": activate_mock_subscription(user).as_dict()}


@router.post("/mock/cancel")
def mock_cancel(user: User = Depends(current_user)) -> dict:
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    return {"membership": cancel_mock_subscription(user).as_dict()}


@router.post("/mock/expire")
def mock_expire(user: User = Depends(current_user)) -> dict:
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    return {"membership": expire_mock_subscription(user).as_dict()}


@router.post("/mock/payment-failed")
def mock_payment_failed(user: User = Depends(current_user)) -> dict:
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    return {"membership": fail_mock_payment(user).as_dict()}
