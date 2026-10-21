"""Pagos MotorCriollo por Stripe (publicar y comisión).

Verificación estricta: una sesión de Stripe solo vale para el tipo (publish/commission),
el anuncio o venta, el monto y la moneda con que se creó, y solo una vez.
"""
from __future__ import annotations

from typing import Any

from config import stripe_secret, stripe_webhook_secret

APP_TAG = "motorcriollo"
CURRENCY = "usd"
KIND_PUBLISH = "publish"
KIND_COMMISSION = "commission"
_TARGET_KEY = {KIND_PUBLISH: "listing_id", KIND_COMMISSION: "deal_id"}


def amount_cents(amount_usd: int) -> int:
    return max(100, int(amount_usd) * 100)


def create_checkout(
    *,
    amount_usd: int,
    name: str,
    description: str,
    success_url: str,
    cancel_url: str,
    metadata: dict | None = None,
) -> dict:
    secret = stripe_secret()
    if not secret:
        raise RuntimeError("STRIPE_SECRET_KEY no configurada")
    cents = amount_cents(amount_usd)
    import stripe

    stripe.api_key = secret
    meta = {"app": APP_TAG, **(metadata or {}), "amount_cents": str(cents)}
    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        line_items=[
            {
                "quantity": 1,
                "price_data": {
                    "currency": CURRENCY,
                    "unit_amount": cents,
                    "product_data": {
                        "name": (name or "MotorCriollo")[:80],
                        "description": (description or "")[:200],
                    },
                },
            }
        ],
        metadata=meta,
        payment_intent_data={"metadata": meta},
    )
    url = session.url or ""
    if not url:
        raise RuntimeError("Stripe no devolvió URL")
    return {"url": url, "id": session.id, "amount_cents": cents}


def create_publish_checkout(
    *, amount_usd: int, listing_id: int, title: str, success_url: str, cancel_url: str
) -> dict:
    return create_checkout(
        amount_usd=amount_usd,
        name=f"Publicar en MotorCriollo — {(title or '')[:50]}",
        description="Pago para publicar el anuncio (Binance Card Venezuela, tarjeta o USDC)",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"kind": KIND_PUBLISH, "listing_id": str(int(listing_id))},
    )


def create_commission_checkout(
    *,
    amount_usd: int,
    deal_id: int,
    conversation_id: int,
    title: str,
    success_url: str,
    cancel_url: str,
) -> dict:
    name = (title or "MotorCriollo")[:80]
    return create_checkout(
        amount_usd=amount_usd,
        name=f"Comisión MotorCriollo — {name}",
        description="Comisión por venta aceptada (Binance Card Venezuela, tarjeta o USDC)",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "kind": KIND_COMMISSION,
            "deal_id": str(int(deal_id)),
            "conversation_id": str(int(conversation_id)),
        },
    )


def retrieve_session(session_id: str):
    secret = stripe_secret()
    if not secret:
        return None
    import stripe

    stripe.api_key = secret
    return stripe.checkout.Session.retrieve(session_id)


def _get(obj: Any, key: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return obj[key]
    except Exception:
        return getattr(obj, key, default)


def session_metadata(sess: Any) -> dict:
    meta = _get(sess, "metadata") or {}
    try:
        if hasattr(meta, "to_dict"):  # StripeObject (stripe-python >= 12)
            meta = meta.to_dict()
        return {str(k): str(v) for k, v in dict(meta).items()}
    except Exception:
        return {}


def verify_paid_session(
    sess: Any,
    *,
    kind: str,
    target_id: int,
    expected_cents: int,
    stored_session_id: str,
) -> tuple[bool, str]:
    """Devuelve (ok, motivo). ok=True solo si la sesión pagada corresponde exactamente."""
    if kind not in _TARGET_KEY:
        return False, "tipo inválido"
    if not sess:
        return False, "sesión no encontrada"
    sid = str(_get(sess, "id") or "")
    if not sid or not stored_session_id or sid != str(stored_session_id):
        return False, "la sesión no es la que se creó para este pago"
    if str(_get(sess, "payment_status") or "") != "paid":
        return False, "pago no confirmado"
    status = _get(sess, "status")
    if status is not None and str(status) != "complete":
        return False, "sesión no completada"
    if str(_get(sess, "mode") or "payment") != "payment":
        return False, "modo inválido"
    meta = session_metadata(sess)
    if meta.get("app") != APP_TAG:
        return False, "sesión de otra aplicación"
    if meta.get("kind") != kind:
        return False, "el pago es de otro tipo"
    if meta.get(_TARGET_KEY[kind]) != str(int(target_id)):
        return False, "el pago es de otro anuncio o venta"
    if str(_get(sess, "currency") or "").lower() != CURRENCY:
        return False, "moneda inválida"
    try:
        total = int(_get(sess, "amount_total") or 0)
    except (TypeError, ValueError):
        total = 0
    if int(expected_cents) <= 0 or total != int(expected_cents):
        return False, "monto incorrecto"
    return True, "ok"


def construct_webhook_event(payload: bytes, sig_header: str):
    """Verifica la firma del webhook con STRIPE_WEBHOOK_SECRET. Lanza error si no vale."""
    secret = stripe_webhook_secret()
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET no configurada")
    import stripe

    return stripe.Webhook.construct_event(payload, sig_header or "", secret)
