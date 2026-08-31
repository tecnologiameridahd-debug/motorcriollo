"""Comisión MotorCriollo por Stripe (tarjeta y crypto si está activo en el Dashboard)."""
from __future__ import annotations

from config import PUBLIC_BASE_URL, stripe_secret


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
    cents = max(100, int(amount_usd) * 100)
    import stripe

    stripe.api_key = secret
    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        line_items=[
            {
                "quantity": 1,
                "price_data": {
                    "currency": "usd",
                    "unit_amount": cents,
                    "product_data": {
                        "name": (name or "MotorCriollo")[:80],
                        "description": (description or "")[:200],
                    },
                },
            }
        ],
        metadata={"app": "motorcriollo", **(metadata or {})},
    )
    url = session.url or ""
    if not url:
        raise RuntimeError("Stripe no devolvió URL")
    return {"url": url, "id": session.id}


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
        description="Comisión por venta aceptada (tarjeta o crypto)",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "kind": "commission",
            "deal_id": str(deal_id),
            "conversation_id": str(conversation_id),
        },
    )


def retrieve_session(session_id: str):
    secret = stripe_secret()
    if not secret:
        return None
    import stripe

    stripe.api_key = secret
    return stripe.checkout.Session.retrieve(session_id)
