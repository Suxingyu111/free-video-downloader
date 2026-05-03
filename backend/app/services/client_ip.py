from __future__ import annotations

from fastapi import Request

from app.services.app_config import load_config


def client_ip_from_request(request: Request) -> str:
    if load_config().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip() or "unknown"
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip() or "unknown"
    if request.client:
        return request.client.host
    return "unknown"
