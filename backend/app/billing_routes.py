from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import stripe
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth_routes import current_user
from app.services.app_config import load_config
from app.services.auth_service import User
from app.services.billing_service import (
    activate_mock_subscription,
    begin_stripe_event_processing,
    cancel_mock_subscription,
    complete_stripe_checkout_attempt,
    confirm_stripe_checkout_session,
    create_mock_checkout,
    credit_pack_from_price_id,
    ensure_stripe_customer_id,
    expire_mock_subscription,
    fail_mock_payment,
    grant_credit_pack,
    get_open_stripe_checkout_attempt,
    get_membership,
    mark_stripe_event_pending,
    mark_stripe_event_processed,
    mark_stripe_invoice_payment_failed,
    record_stripe_checkout_attempt,
    StripeCheckoutNotReadyError,
    StripeCheckoutOwnershipError,
    StripeEventInProgress,
    upsert_stripe_checkout_session,
    upsert_stripe_invoice_paid,
    upsert_stripe_subscription,
)
from app.services.database import connect
from app.services.plan_catalog import get_credit_pack


router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutConfirmRequest(BaseModel):
    session_id: str


class CheckoutRequest(BaseModel):
    return_url: str | None = None
    purchase_type: str = "subscription"
    pack_id: str | None = None


def _url_origin(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _checkout_return_base_url(
    configured_url: str,
    request: Request,
    requested_return_url: str | None,
) -> str:
    configured_origin = _url_origin(configured_url)
    request_origin = _url_origin(request.headers.get("origin"))
    requested_origin = _url_origin(requested_return_url)
    allowed_origins = {origin for origin in (configured_origin, request_origin) if origin}
    if requested_origin and requested_origin in allowed_origins:
        return requested_origin
    return configured_origin or configured_url.rstrip("/")


@router.get("/status")
def billing_status(user: User = Depends(current_user)) -> dict:
    return {"membership": get_membership(user.id).as_dict(), "mode": load_config().billing_mode}


@router.post("/checkout")
def billing_checkout(
    request: Request,
    payload: CheckoutRequest | None = Body(default=None),
    user: User = Depends(current_user),
) -> dict:
    config = load_config()
    purchase_type = payload.purchase_type if payload else "subscription"
    if purchase_type == "credit_pack":
        if not payload or not payload.pack_id:
            raise HTTPException(status_code=400, detail="缺少按量包类型")
        pack = get_credit_pack(payload.pack_id)
        if config.billing_mode == "mock":
            credit_pack = grant_credit_pack(
                user.id,
                pack.id,
                source="mock",
                payment_reference=f"mock_{pack.id}",
            )
            return {"mode": "mock", "credit_pack": credit_pack, "url": "/#pricing"}
        price_id = getattr(config, pack.stripe_config_field)
        if not config.stripe_secret_key or not price_id:
            raise HTTPException(status_code=503, detail="Stripe 按量包支付尚未配置")
        return_base_url = _checkout_return_base_url(
            config.public_app_url,
            request,
            payload.return_url,
        )
        stripe.api_key = config.stripe_secret_key
        customer_id = ensure_stripe_customer_id(
            user,
            lambda: stripe.Customer.create(
                email=user.email,
                metadata={"saveany_user_id": user.id},
            ).id,
        )
        session = stripe.checkout.Session.create(
            mode="payment",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{return_base_url}/#pricing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{return_base_url}/#pricing?checkout=cancel",
            client_reference_id=user.id,
            metadata={
                "saveany_user_id": user.id,
                "purchase_type": "credit_pack",
                "pack_id": pack.id,
            },
        )
        record_stripe_checkout_attempt(user.id, session.id, session.url, return_base_url)
        return {"mode": "stripe", "url": session.url, "session_id": session.id}
    if purchase_type != "subscription":
        raise HTTPException(status_code=400, detail="未知购买类型")
    membership = get_membership(user.id)
    if membership.active:
        raise HTTPException(status_code=409, detail="你已经是专业版会员，请前往会员管理。")
    if config.billing_mode == "mock":
        return create_mock_checkout(user)
    if config.billing_mode == "stripe":
        if not config.stripe_secret_key or not config.stripe_pro_monthly_price_id:
            raise HTTPException(status_code=503, detail="Stripe 支付尚未配置")
        return_base_url = _checkout_return_base_url(config.public_app_url, request, payload.return_url if payload else None)
        open_attempt = get_open_stripe_checkout_attempt(user.id, return_base_url if payload else None)
        if open_attempt is not None:
            return {
                "mode": "stripe",
                "url": open_attempt["stripe_checkout_url"],
                "session_id": open_attempt["stripe_checkout_session_id"],
            }
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
            success_url=f"{return_base_url}/#pricing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{return_base_url}/#pricing?checkout=cancel",
            client_reference_id=user.id,
            subscription_data={"metadata": {"saveany_user_id": user.id}},
            metadata={"saveany_user_id": user.id},
        )
        record_stripe_checkout_attempt(user.id, session.id, session.url, return_base_url)
        return {"mode": "stripe", "url": session.url, "session_id": session.id}
    raise HTTPException(status_code=503, detail="Stripe 支付尚未配置")


@router.post("/checkout/confirm")
def billing_checkout_confirm(
    payload: CheckoutConfirmRequest,
    user: User = Depends(current_user),
) -> dict:
    config = load_config()
    session_id = payload.session_id.strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="缺少 Stripe Checkout Session ID")
    if config.billing_mode != "stripe":
        raise HTTPException(status_code=404, detail="Stripe 支付确认仅在 Stripe 模式可用")
    if not config.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe 支付尚未配置")

    stripe.api_key = config.stripe_secret_key
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
        membership = confirm_stripe_checkout_session(
            user,
            session,
            lambda subscription_id: stripe.Subscription.retrieve(subscription_id),
        )
    except StripeCheckoutOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except StripeCheckoutNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Stripe 确认失败，请稍后重试") from exc
    return {"membership": membership.as_dict(), "mode": "stripe"}


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
    try:
        should_process = begin_stripe_event_processing(event_id, event_type, payload)
    except StripeEventInProgress as exc:
        raise HTTPException(status_code=409, detail="Stripe webhook 事件正在处理") from exc
    if not should_process:
        return {"ok": True}

    try:
        if event_type == "checkout.session.completed":
            checkout_session = event["data"]["object"]
            upsert_stripe_checkout_session(checkout_session)
            metadata = checkout_session.get("metadata") or {}
            if checkout_session.get("mode") == "payment" and metadata.get("purchase_type") == "credit_pack":
                pack_id = metadata.get("pack_id")
                user_id = metadata.get("saveany_user_id") or checkout_session.get("client_reference_id")
                if not pack_id or not user_id:
                    raise ValueError("Stripe credit pack checkout is missing metadata")
                price_id = None
                line_items = ((checkout_session.get("line_items") or {}).get("data") or [])
                if line_items:
                    price_id = (line_items[0].get("price") or {}).get("id")
                if not price_id:
                    raise ValueError("Stripe credit pack price does not match pack metadata")
                configured_pack_id = credit_pack_from_price_id(price_id)
                if configured_pack_id != pack_id:
                    raise ValueError("Stripe credit pack price does not match pack metadata")
                grant_credit_pack(
                    user_id,
                    pack_id,
                    source="stripe",
                    payment_reference=checkout_session.get("payment_intent") or checkout_session["id"],
                    stripe_price_id=price_id,
                )
            if checkout_session.get("id"):
                complete_stripe_checkout_attempt(checkout_session["id"])
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


@router.post("/mock/credit-pack/{pack_id}")
def mock_credit_pack(pack_id: str, user: User = Depends(current_user)) -> dict:
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    pack = get_credit_pack(pack_id)
    return {
        "credit_pack": grant_credit_pack(
            user.id,
            pack.id,
            source="mock",
            payment_reference=f"mock_{pack.id}",
        )
    }


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
