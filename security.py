"""Seguridad: rate limits en memoria, IP del cliente, cabeceras y chequeo de origen (CSRF)."""
from __future__ import annotations

import threading
import time
from collections import deque
from urllib.parse import urlsplit

from fastapi import Request


class RateLimiter:
    """Ventana deslizante en memoria. Suficiente para una sola instancia (Render Starter)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: int) -> bool:
        """Registra un intento. Devuelve False si se pasó del límite."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self._hits) > 50_000:
                self._gc(now)
            return True

    def count(self, key: str, window: int) -> int:
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return 0
            while q and q[0] <= now - window:
                q.popleft()
            return len(q)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)

    def _gc(self, now: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or q[-1] < now - 86400]:
            self._hits.pop(k, None)


limiter = RateLimiter()

# (límite, ventana en segundos)
LIMITS = {
    "login_ip": (10, 900),
    "login_email": (8, 900),
    "signup_ip": (5, 3600),
    "forgot_ip": (5, 3600),
    "forgot_email": (3, 3600),
    "report_ip": (10, 3600),
    "report_listing_ip": (1, 86400),
    "chat_user": (20, 60),
    "chat_user_day": (300, 86400),
    "chat_mail": (1, 600),
    "verify_mail_user": (3, 3600),
    "admin_ip": (5, 900),
    "admin_global": (20, 3600),
}


def allow(bucket: str, ident: str) -> bool:
    limit, window = LIMITS[bucket]
    return limiter.hit(f"{bucket}:{ident}", limit, window)


def blocked(bucket: str, ident: str) -> bool:
    """True si ya se alcanzó el límite (sin registrar un intento nuevo)."""
    limit, window = LIMITS[bucket]
    return limiter.count(f"{bucket}:{ident}", window) >= limit


def client_ip(request: Request) -> str:
    # Render va detrás de Cloudflare: CF-Connecting-IP lo pone el proxy y no el cliente.
    for h in ("cf-connecting-ip", "true-client-ip"):
        v = (request.headers.get(h) or "").strip()
        if v:
            return v[:64]
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if xff:
        return xff[:64]
    return (request.client.host if request.client else "") or "?"


CSP = "; ".join(
    [
        "default-src 'self'",
        # Las plantillas usan <script> inline y onclick=; sin build step no hay nonces.
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com data:",
        "img-src 'self' data: https:",
        "connect-src 'self'",
        "frame-src 'none'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self' https://checkout.stripe.com https://accounts.google.com https://appleid.apple.com",
        "frame-ancestors 'none'",
    ]
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
HSTS = "max-age=31536000; includeSubDomains"


def apply_security_headers(request: Request, response, https: bool) -> None:
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if https:
        response.headers.setdefault("Strict-Transport-Security", HSTS)


# Rutas que reciben POST legítimos desde otro origen.
CSRF_EXEMPT = ("/stripe/webhook", "/auth/apple/callback")


def same_origin_ok(request: Request, extra_hosts: set[str]) -> bool:
    """Rechaza POST/PUT/DELETE cuyo Origin (o Referer) sea de otro sitio."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    if request.url.path.startswith(CSRF_EXEMPT):
        return True
    host = (request.headers.get("host") or "").lower()
    allowed = {h for h in ({host} | extra_hosts) if h}
    origin = request.headers.get("origin")
    if origin is not None:
        if origin == "null":
            return False
        return (urlsplit(origin).netloc or "").lower() in allowed
    ref = request.headers.get("referer")
    if ref:
        return (urlsplit(ref).netloc or "").lower() in allowed
    # Sin Origin ni Referer (clientes viejos / herramientas): las cookies SameSite=Lax
    # ya bloquean el POST cross-site del navegador.
    return True
