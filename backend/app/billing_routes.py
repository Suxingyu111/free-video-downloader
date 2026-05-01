from __future__ import annotations

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth_routes import current_user
from app.services.app_config import load_config
from app.services.auth_service import User
from app.services.billing_service import (
    activate_mock_subscription,
    begin_stripe_event_processing,
    cancel_mock_subscription,
    create_mock_checkout,
    ensure_stripe_customer_id,
    expire_mock_subscription,
    fail_mock_payment,
    get_membership,
    mark_stripe_event_pending,
    mark_stripe_event_processed,
    mark_stripe_invoice_payment_failed,
    upsert_stripe_checkout_session,
    upsert_stripe_invoice_paid,
    upsert_stripe_subscription,
)
from app.services.database import connect


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
    if config.billing_mode == "stripe":
        if not config.stripe_secret_key or not config.stripe_pro_monthly_price_id:
            raise HTTPException(status_code=503, detail="Stripe 支付尚未配置")
        stripe.api_key = config.stripe_secret_key
        customer_id = ensure_stripe_customer_id(
            user,
            lambda: stripe.Customer.create(
                email=user.email,
                metadata={"saveany_user_id": user.id},
            ).id,
        )
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": config.stripe_pro_monthly_price_id, "quantity": 1}],
            success_url=f"{config.public_app_url}/#pricing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{config.public_app_url}/#pricing?checkout=cancel",
            client_reference_id=user.id,
            subscription_data={"metadata": {"saveany_user_id": user.id}},
            metadata={"saveany_user_id": user.id},
        )
        return {"mode": "stripe", "url": session.url, "session_id": session.id}
    raise HTTPException(status_code=503, detail="Stripe 支付尚未配置")


@router.post("/portal")
def billing_portal(user: User = Depends(current_user)) -> dict:
    config = load_config()
    if config.billing_mode == "mock":
        return {"mode": "mock", "url": "/#pricing"}
    if not config.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe 支付尚未配置")
    membership = get_membership(user.id)
    conn = connect()
    try:
        row = conn.execute(
            """
            select stripe_customer_id from subscriptions
            where user_id = ?
            order by updated_at desc
            limit 1
            """,
            (user.id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None or not row["stripe_customer_id"]:
        raise HTTPException(status_code=404, detail="还没有可管理的 Stripe 会员订阅")
    stripe.api_key = config.stripe_secret_key
    session = stripe.billing_portal.Session.create(
        customer=row["stripe_customer_id"],
        return_url=f"{config.public_app_url}/#pricing",
    )
    return {"mode": "stripe", "url": session.url, "membership": membership.as_dict()}


@router.post("/webhook")
async def stripe_webhook(request: Request) -> dict[str, bool]:
    config = load_config()
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, signature, config.stripe_webhook_secret)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Stripe webhook 签名验证失败") from exc

    event_id = event.get("id")
    event_type = event.get("type")
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Stripe webhook 缺少事件 ID")
    if not begin_stripe_event_processing(event_id, event_type, payload):
        return {"ok": True}

    try:
        if event_type == "checkout.session.completed":
            upsert_stripe_checkout_session(event["data"]["object"])
        elif event_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            upsert_stripe_subscription(event["data"]["object"])
        elif event_type == "invoice.paid":
            upsert_stripe_invoice_paid(event["data"]["object"])
        elif event_type == "invoice.payment_failed":
            mark_stripe_invoice_payment_failed(event["data"]["object"])
        mark_stripe_event_processed(event_id)
    except Exception:
        mark_stripe_event_pending(event_id)
        raise
    return {"ok": True}


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
