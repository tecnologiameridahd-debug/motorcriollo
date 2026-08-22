"""Correo transaccional MotorCriollo vía SendGrid (misma API que DateRadar/CoachRadar)."""
from __future__ import annotations

import os

import requests

SITE = (
    os.environ.get("MOTORCRIOLLO_PUBLIC_URL") or "https://www.motorcriollo.com"
).rstrip("/")
LOGO = f"{SITE}/static/logo-512.jpg"
_BG = "#0b0f0a"
_SURFACE = "#121a12"
_TEXT = "#f2f7ee"
_GREEN = "#4ade80"
_ON = "#052e0f"

LAST = {"ok": None, "status": None, "error": None, "from": None}


def sendgrid_api_key() -> str:
    return (
        os.environ.get("SENDGRID_API_KEY") or os.environ.get("SENDGRID_KEY") or ""
    ).strip()


def from_email() -> str:
    # Por defecto el From ya verificado en SendGrid (CoachRadar).
    # motorcriollo.com aún no está autenticado: si se usa, SendGrid rechaza el envío.
    return (
        os.environ.get("SENDGRID_FROM_EMAIL") or "noreply@coachradar.fit"
    ).strip()


def from_name() -> str:
    return (os.environ.get("SENDGRID_FROM_NAME") or "MotorCriollo").strip()


def reply_to() -> str:
    return (os.environ.get("SENDGRID_REPLY_TO") or "soporte@motorcriollo.com").strip()


def fallback_from() -> str:
    return (
        os.environ.get("SENDGRID_FROM_FALLBACK") or "noreply@coachradar.fit"
    ).strip()


def email_ready() -> bool:
    key = sendgrid_api_key()
    return bool(key) and key.startswith("SG.")


def email_status() -> dict:
    key = sendgrid_api_key()
    return {
        "configured": email_ready(),
        "from_email": from_email(),
        "reply_to": reply_to(),
        "fallback_from": fallback_from(),
        "key_prefix": (key[:5] + "…") if len(key) >= 5 else "(vacía)",
        "last_ok": LAST["ok"],
        "last_status": LAST["status"],
        "last_error": LAST["error"],
        "last_from": LAST["from"],
    }


def _html(heading: str, paragraphs: list[str], btn: str, url: str) -> str:
    rows = "".join(
        f'<p style="margin:0 0 16px;line-height:1.55;color:{_TEXT}">{p}</p>'
        for p in paragraphs
    )
    return f"""<!doctype html>
<html lang="es"><body style="margin:0;padding:32px 16px;background:{_BG};font-family:system-ui,sans-serif">
<table role="presentation" width="100%"><tr><td align="center">
<table width="480" style="max-width:480px;width:100%;background:{_SURFACE};border-radius:16px">
<tr><td align="center" style="padding:28px 28px 8px">
<img src="{LOGO}" width="56" height="56" alt="MotorCriollo" style="border-radius:12px">
</td></tr>
<tr><td style="padding:8px 28px 8px">
<h1 style="margin:0 0 16px;color:{_TEXT};font-size:20px;text-align:center">{heading}</h1>
{rows}
</td></tr>
<tr><td align="center" style="padding:8px 28px 28px">
<a href="{url}" style="display:inline-block;background:{_GREEN};color:{_ON};font-weight:700;text-decoration:none;padding:12px 22px;border-radius:999px">{btn}</a>
</td></tr>
<tr><td style="padding:16px 28px;border-top:1px solid rgba(255,255,255,.08)">
<p style="margin:0;color:#9db296;font-size:12px;text-align:center">MotorCriollo · motorcriollo.com</p>
</td></tr>
</table></td></tr></table>
</body></html>"""


def _post(to: str, subject: str, text: str, html: str, sender: str) -> tuple[int, str]:
    key = sendgrid_api_key()
    r = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": sender, "name": from_name()},
            "reply_to": {"email": reply_to()},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text},
                {"type": "text/html", "value": html},
            ],
        },
        timeout=15,
    )
    return r.status_code, (r.text or "")[:400]


def _send(to_email: str, subject: str, text: str, html: str) -> bool:
    key = sendgrid_api_key()
    to = (to_email or "").strip()
    if not key or not to or "@" not in to:
        LAST.update({"ok": False, "status": None, "error": "sin key o destino", "from": None})
        print("[email] skip — sin key o destino")
        return False
    senders = [from_email()]
    fb = fallback_from()
    if fb and fb.lower() not in {s.lower() for s in senders}:
        senders.append(fb)
    last_status, last_body, used = 0, "", senders[0]
    try:
        for sender in senders:
            used = sender
            last_status, last_body = _post(to, subject, text, html, sender)
            if last_status in (200, 202):
                LAST.update(
                    {"ok": True, "status": last_status, "error": None, "from": used}
                )
                print(f"[email] OK → {to} from={used} status={last_status}")
                return True
            print(f"[email] FAIL → {to} from={used} status={last_status} body={last_body}")
            if last_status not in (400, 403):
                break
        LAST.update(
            {"ok": False, "status": last_status, "error": last_body or "fail", "from": used}
        )
        return False
    except Exception as e:
        LAST.update(
            {"ok": False, "status": None, "error": f"{type(e).__name__}: {e}", "from": used}
        )
        print(f"[email] ERROR {type(e).__name__}: {e}")
        return False


def send_verify(to_email: str, name: str, token: str) -> bool:
    url = f"{SITE}/verificar?token={token}"
    return _send(
        to_email,
        "Confirma tu correo en MotorCriollo",
        f"Hola {name}. Confirma tu correo: {url}",
        _html(
            "Confirma tu correo",
            [f"Hola {name}. Toca el botón para confirmar que este email es tuyo."],
            "Confirmar correo",
            url,
        ),
    )


def send_welcome(to_email: str, name: str) -> bool:
    return _send(
        to_email,
        "Bienvenido a MotorCriollo",
        f"Hola {name}. ¡Bienvenido a MotorCriollo! Tu cuenta ya está lista: {SITE}",
        _html(
            "Bienvenido a MotorCriollo",
            [f"Hola {name}. Tu cuenta ya está lista — publica tu carro o busca el próximo."],
            "Abrir MotorCriollo",
            SITE,
        ),
    )


def send_reset(to_email: str, name: str, token: str) -> bool:
    url = f"{SITE}/reset?token={token}"
    return _send(
        to_email,
        "Cambia tu contraseña de MotorCriollo",
        f"Hola {name}. Cambia tu contraseña: {url}",
        _html(
            "Nueva contraseña",
            [f"Hola {name}. Este enlace caduca en 2 horas."],
            "Elegir contraseña",
            url,
        ),
    )


def send_buyer_message(
    to_email: str,
    seller_name: str,
    listing_title: str,
    listing_id: int,
    buyer_name: str,
    buyer_email: str,
    buyer_phone: str,
    message: str,
) -> bool:
    """Notifica al vendedor que un comprador dejó un mensaje sobre su publicación."""
    url = f"{SITE}/listing/{listing_id}"
    contacto = buyer_phone or buyer_email or "sin datos de contacto"
    text = (
        f"Hola {seller_name}. {buyer_name} está interesado en tu publicación "
        f"'{listing_title}'.\n\nMensaje: {message}\n\nContacto: {contacto}\n\nVer publicación: {url}"
    )
    paras = [
        f"Hola {seller_name}. <b>{buyer_name}</b> está interesado en tu publicación "
        f"«{listing_title}».",
        f"Mensaje: {message}",
        f"Contacto del comprador: {contacto}",
    ]
    return _send(
        to_email,
        f"Nuevo mensaje sobre tu {listing_title}",
        text,
        _html("Tienes un mensaje nuevo", paras, "Ver publicación", url),
    )


def send_test(to_email: str) -> bool:
    return _send(
        to_email,
        "MotorCriollo — prueba de correo",
        "Si lees esto, el correo de MotorCriollo funciona.",
        _html(
            "Prueba de correo",
            ["Si ves esto, MotorCriollo ya puede enviar emails."],
            "Abrir MotorCriollo",
            SITE,
        ),
    )
