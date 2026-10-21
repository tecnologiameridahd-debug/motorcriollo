"""MotorCriollo — marketplace de carros usados (estilo Facebook Marketplace)."""
from __future__ import annotations

import hmac
import os
import re
import secrets
import threading
import unicodedata
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    BASE_DIR,
    COMMISSION_USD,
    IS_PROD,
    MAX_UPLOAD_BYTES,
    PASSWORD_MIN_LEN,
    PRIVATE_DIR,
    demo_enabled,
    stripe_webhook_secret,
    PUBLISH_FEE_USD,
    KYC_DIR,
    MAX_PHOTOS,
    OAUTH_STATE_COOKIE,
    PAY_INFO,
    PERSISTENT,
    PORT,
    PUBLIC_BASE_URL,
    SESSION_COOKIE,
    SESSION_DAYS,
    UPLOAD_DIR,
    admin_password,
    apple_enabled,
    google_enabled,
    stripe_enabled,
    stripe_mode,
)
from email_utils import (
    email_ready,
    email_status,
    send_chat_notice,
    send_kyc_decision,
    send_reset,
    send_verify,
    send_welcome,
)
from oauth import apple_authorize_url, apple_user, google_authorize_url, google_user
from seed import seed
from blog_posts import BLOG_POSTS
from storage import (
    BRANDS,
    CITY_PAGES,
    CONDITIONS,
    FUEL_TYPES,
    TRANSMISSIONS,
    VE_STATES,
    VE_STATE_CITIES,
    accept_deal,
    add_chat_message,
    add_listing_photo,
    add_rating,
    add_report,
    admin_from_token,
    approve_kyc,
    browse_listings,
    can_publish,
    cancel_deal,
    confirm_deal_paid,
    count_active_listings,
    close_report,
    count_deals_open,
    count_kyc_pending,
    count_reports_open,
    count_unread,
    count_users,
    create_admin_session,
    create_listing,
    create_session,
    create_user,
    delete_admin_session,
    delete_listing,
    delete_session,
    delete_user,
    get_conversation,
    get_deal,
    get_deal_by_conversation,
    get_listing,
    get_or_create_conversation,
    get_setting,
    get_user,
    hide_demo_now,
    get_user_by_email,
    has_rated_deal,
    init_db,
    is_favorite,
    list_all_listings,
    list_chat_messages,
    list_conversations,
    list_deals,
    list_favorites,
    list_kyc,
    list_reports,
    list_user_listings,
    list_users_admin,
    login,
    make_email_token,
    mark_conversation_read,
    reject_kyc,
    revoke_kyc,
    set_deal_proof,
    set_deal_stripe_session,
    set_setting,
    seller_reputation,
    set_password,
    submit_kyc,
    take_email_token,
    toggle_favorite,
    update_listing,
    update_profile,
    upsert_oauth_user,
    user_from_session,
    UnverifiedAccountError,
    claim_stripe_session,
    listing_file_paths,
    user_file_paths,
)
from security import (
    allow as rl_allow,
    apply_security_headers,
    blocked as rl_blocked,
    client_ip,
    limiter,
    same_origin_ok,
)
import stripe_pay

ADMIN_COOKIE = "mc_admin"
OAUTH_NEXT_COOKIE = "mc_next"

app = FastAPI(
    title="MotorCriollo",
    # /docs, /redoc y /openapi.json solo en local.
    docs_url=None if IS_PROD else "/docs",
    redoc_url=None if IS_PROD else "/redoc",
    openapi_url=None if IS_PROD else "/openapi.json",
)


def _extra_hosts() -> set[str]:
    hosts = {"motorcriollo.store", "www.motorcriollo.store"}
    if PUBLIC_BASE_URL:
        from urllib.parse import urlsplit

        hosts.add(urlsplit(PUBLIC_BASE_URL).netloc.lower())
    return hosts


_EXTRA_HOSTS = _extra_hosts()


@app.middleware("http")
async def _security_middleware(request: Request, call_next):
    if not same_origin_ok(request, _EXTRA_HOSTS):
        resp = PlainTextResponse("Solicitud bloqueada (origen no permitido).", status_code=403)
    else:
        resp = await call_next(request)
    https = IS_PROD or request.url.scheme == "https" or (
        request.headers.get("x-forwarded-proto") == "https"
    )
    apply_security_headers(request, resp, https)
    return resp
app.mount("/static/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.on_event("startup")
def _startup():
    init_db()
    seed()
    try:
        c = (get_setting("commission") or "").strip()
        if not c or c == "20":
            set_setting("commission", str(int(COMMISSION_USD)))
        if not (get_setting("publish_fee") or "").strip():
            set_setting("publish_fee", str(int(PUBLISH_FEE_USD)))
    except Exception:
        pass


def me(request: Request):
    return user_from_session(request.cookies.get(SESSION_COOKIE))


def _admin(request: Request) -> bool:
    return admin_from_token(request.cookies.get(ADMIN_COOKIE))


def _page(request: Request, name: str, **ctx):
    user = me(request)
    ctx.setdefault("me", user)
    ctx.setdefault("is_admin", _admin(request))
    ctx.setdefault("can_publish", can_publish(user))
    ctx.setdefault("_base", _base(request))
    ctx.setdefault("_canon_base", _public_base(request))
    ctx.setdefault("google_ok", google_enabled())
    ctx.setdefault("apple_ok", apple_enabled())
    ctx.setdefault("brands", BRANDS)
    ctx.setdefault("transmissions", TRANSMISSIONS)
    ctx.setdefault("fuel_types", FUEL_TYPES)
    ctx.setdefault("conditions", CONDITIONS)
    ctx.setdefault("commission", _commission())
    ctx.setdefault("publish_fee", _publish_fee())
    ctx.setdefault("pay_info", _pay_info())
    ctx.setdefault("pay_usdt_trc20", (get_setting("pay_usdt_trc20") or "").strip())
    ctx.setdefault("pay_usdt_erc20", (get_setting("pay_usdt_erc20") or "").strip())
    ctx.setdefault("stripe_ok", stripe_enabled())
    ctx.setdefault("ve_states", VE_STATES)
    ctx.setdefault("unread_n", count_unread(user["id"]) if user else 0)
    ctx.setdefault("listing_slug", listing_slug)
    ctx.setdefault("canonical", "")
    ctx.setdefault("state_pages", VE_STATE_CITIES)
    ctx.setdefault("blog_posts", BLOG_POSTS)
    ctx.setdefault("password_min", PASSWORD_MIN_LEN)
    ctx.setdefault(
        "fav_ids",
        {x["id"] for x in list_favorites(user["id"])} if user else set(),
    )
    return templates.TemplateResponse(request, name, ctx)


def _show_demo() -> bool:
    """Los carros demo solo se ven si el modo demo está encendido y no se ocultaron."""
    return demo_enabled() and not hide_demo_now()


def _too_many(request: Request, name: str, msg: str = "", **ctx):
    resp = _page(
        request, name,
        error=msg or "Demasiados intentos. Espera unos minutos y vuelve a probar.",
        **ctx,
    )
    resp.status_code = 429
    return resp


def _commission() -> int:
    raw = (get_setting("commission") or "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return int(COMMISSION_USD)


def _publish_fee() -> int:
    raw = (get_setting("publish_fee") or "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return int(PUBLISH_FEE_USD)


def _pay_info() -> str:
    zelle = (get_setting("pay_zelle") or "").strip()
    pm = (get_setting("pay_pago_movil") or "").strip()
    extra = (get_setting("pay_info") or "").strip()
    parts = []
    if "binance card" not in extra.lower():
        parts.append("Aceptamos Binance Card Venezuela (Mastercard vía Stripe).")
    if zelle:
        parts.append(f"Zelle: {zelle}")
    if pm:
        parts.append(f"Pago Móvil: {pm}")
    if extra:
        parts.append(extra)
    trc = (get_setting("pay_usdt_trc20") or "").strip()
    erc = (get_setting("pay_usdt_erc20") or "").strip()
    if trc:
        parts.append(f"USDT TRC20: {trc}")
    if erc:
        parts.append(f"USDT ERC20: {erc}")
    return " · ".join(parts) if parts else PAY_INFO


def _queue_mail(fn, *args, **kwargs) -> None:
    if not email_ready():
        return

    def _run():
        try:
            fn(*args, **kwargs)
        except Exception as e:
            print(f"[mail] {type(e).__name__}: {e}")

    threading.Thread(target=_run, name="mc-mail", daemon=True).start()


def _safe_next(nxt: str) -> str:
    nxt = (nxt or "").strip()
    if nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return "/"


def _base(request: Request) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    return str(request.base_url).rstrip("/")


def _set_session(resp, token: str):
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=bool(os.environ.get("RENDER") or PUBLIC_BASE_URL.startswith("https")),
    )
    return resp


_PHOTO_MAGIC = {
    ".jpg": lambda d: d.startswith(b"\xff\xd8\xff"),
    ".jpeg": lambda d: d.startswith(b"\xff\xd8\xff"),
    ".png": lambda d: d.startswith(b"\x89PNG\r\n\x1a\n"),
    ".gif": lambda d: d.startswith((b"GIF87a", b"GIF89a")),
    ".webp": lambda d: d.startswith(b"RIFF") and d[8:12] == b"WEBP",
}


async def _read_limited(photo: UploadFile) -> bytes:
    size = getattr(photo, "size", None)
    if size is not None and int(size) > MAX_UPLOAD_BYTES:
        raise ValueError(f"La foto pesa más de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    data = await photo.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"La foto pesa más de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    return data


PRIVATE_PREFIX = "/privado/"
_PRIVATE_NAME = re.compile(r"^(\d+)_[0-9a-f]{12}\.(jpg|jpeg|png|gif|webp)$")


async def _save_photo(listing_id: int, photo: UploadFile | None, private: bool = False) -> str:
    """Guarda una imagen. private=True: documentos/comprobantes, solo dueño y admin."""
    if not photo or not photo.filename:
        return ""
    ext = Path(photo.filename).suffix.lower()
    check = _PHOTO_MAGIC.get(ext)
    if not check:
        raise ValueError("Foto: usa jpg, png, gif o webp")
    data = await _read_limited(photo)
    if len(data) < 80:
        return ""
    if not check(data):
        raise ValueError("El archivo no es una imagen válida")
    fname = f"{int(listing_id)}_{secrets.token_hex(6)}{ext}"
    dest = os.path.join(PRIVATE_DIR if private else UPLOAD_DIR, fname)
    with open(dest, "wb") as f:
        f.write(data)
    return f"{PRIVATE_PREFIX}{fname}" if private else f"/static/uploads/{fname}"


def _remove_files(paths: list[str]) -> None:
    """Borra archivos subidos (nunca toca static/demo)."""
    for p in paths:
        p = p or ""
        if p.startswith("kyc:"):
            full = os.path.join(KYC_DIR, os.path.basename(p[4:]))
        elif p.startswith(PRIVATE_PREFIX):
            full = os.path.join(PRIVATE_DIR, os.path.basename(p))
        elif p.startswith("/static/uploads/"):
            full = os.path.join(UPLOAD_DIR, os.path.basename(p))
        else:
            continue
        try:
            if os.path.isfile(full):
                os.remove(full)
        except OSError:
            pass


async def _save_kyc_photo(user_id: int, kind: str, photo: UploadFile | None) -> str:
    if not photo or not photo.filename:
        return ""
    ext = Path(photo.filename).suffix.lower()
    check = _PHOTO_MAGIC.get(ext)
    if not check:
        raise ValueError("Foto: usa jpg, png, gif o webp")
    data = await _read_limited(photo)
    if len(data) < 80:
        raise ValueError("La foto está vacía o dañada")
    if not check(data):
        raise ValueError("El archivo no es una imagen válida")
    fname = f"{int(user_id)}_{kind}{ext}"
    dest = os.path.join(KYC_DIR, fname)
    with open(dest, "wb") as f:
        f.write(data)
    return fname


async def _save_listing_photos(listing_id: int, files: list[UploadFile | None]) -> int:
    n = 0
    for i, up in enumerate(files[: MAX_PHOTOS * 2]):
        if not up or not up.filename:
            continue
        path = await _save_photo(listing_id, up)
        if path:
            add_listing_photo(listing_id, path, i)
            n += 1
        if n >= MAX_PHOTOS:
            break
    return n


def _queue_verify_email(user: dict) -> None:
    em = (user.get("email") or "").strip().lower()
    if not email_ready() or not user.get("id") or not em or em.endswith("@demo.motorcriollo"):
        return
    tok = make_email_token(int(user["id"]), "verify", 48)

    def _run():
        send_verify(em, user.get("name") or "hola", tok)

    threading.Thread(target=_run, name="mc-mail-verify", daemon=True).start()


def _queue_welcome_email(user: dict) -> None:
    em = (user.get("email") or "").strip().lower()
    if not email_ready() or not em or em.endswith("@demo.motorcriollo"):
        return

    def _run():
        send_welcome(em, user.get("name") or "hola")

    threading.Thread(target=_run, name="mc-mail-welcome", daemon=True).start()


def _finish_oauth(request: Request, user: dict, is_new: bool = False):
    update_profile(user["id"], email_verified=1)
    if is_new:
        _queue_welcome_email(user)
    token = create_session(user["id"], SESSION_DAYS)
    nxt = _safe_next(request.cookies.get(OAUTH_NEXT_COOKIE) or "")
    resp = RedirectResponse(nxt, status_code=303)
    resp.delete_cookie(OAUTH_NEXT_COOKIE)
    return _set_session(resp, token)


# --------------------------------------------------------------- browse ----

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def home(
    request: Request,
    q: str = "",
    brand: str = "",
    price_min: str = "",
    price_max: str = "",
    year_min: str = "",
    year_max: str = "",
    city: str = "",
    state: str = "",
):
    def _int(v: str):
        v = (v or "").strip()
        return int(v) if v.isdigit() else None

    show_demo = _show_demo()
    listings = browse_listings(
        q=q, brand=brand, price_min=_int(price_min), price_max=_int(price_max),
        year_min=_int(year_min), year_max=_int(year_max), city=city, state=state,
        include_demo=show_demo,
    )
    base = _public_base(request)
    return _page(
        request, "index.html", listings=listings,
        canonical=f"{base}/" if not (q or brand or city or state or price_min or price_max or year_min or year_max) else "",
        filters={
            "q": q, "brand": brand, "price_min": price_min, "price_max": price_max,
            "year_min": year_min, "year_max": year_max, "city": city, "state": state,
        },
        total=count_active_listings(include_demo=show_demo),
    )


def _chat_allowed(user: dict) -> bool:
    uid = str(user["id"])
    return rl_allow("chat_user", uid) and rl_allow("chat_user_day", uid)


def _share(request: Request, listing: dict) -> dict:
    origin = str(request.base_url).rstrip("/")
    if "onrender.com" in origin and PUBLIC_BASE_URL:
        origin = PUBLIC_BASE_URL.rstrip("/")
    if origin.startswith("https://www.motorcriollo.store"):
        origin = "https://motorcriollo.store"
    url = listing_canonical_url(origin, listing)
    price = "{:,}".format(int(listing.get("price") or 0)).replace(",", ".")
    text = f"{listing.get('title') or 'Carro'} ${price} en MotorCriollo"
    full = f"{text} {url}"
    photo = listing.get("photo") or ""
    if photo.startswith("/"):
        photo = _public_base(request) + photo
    return {
        "url": url,
        "text": text,
        "image": photo,
        "wa": "https://wa.me/?text=" + quote(full),
        "fb": "https://www.facebook.com/sharer/sharer.php?u=" + quote(url),
        "x": "https://twitter.com/intent/tweet?text=" + quote(text) + "&url=" + quote(url),
        "sms": "sms:?&body=" + quote(full),
    }


# ---------------------------------------------------------------- SEO duro
_SLUG_BAD = re.compile(r"[^a-z0-9]+")


def _slugify(*parts: str) -> str:
    text = "-".join(str(p or "").strip() for p in parts if str(p or "").strip())
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = _SLUG_BAD.sub("-", text.lower()).strip("-")
    return text or "carro"


def listing_slug(l: dict) -> str:
    base = _slugify(l.get("brand"), l.get("model"), l.get("year"), l.get("city"))
    return f"{base}-{l['id']}"


def listing_canonical_url(origin: str, listing: dict) -> str:
    return f"{origin.rstrip('/')}/carro/{listing_slug(listing)}"


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt(request: Request):
    base = _public_base(request)
    return f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"


@app.get("/sitemap.xml")
def sitemap_xml(request: Request):
    base = _public_base(request)
    urls: list[tuple[str, str]] = [("/", "1.0"), ("/blog", "0.6")]
    for _sslug, _sname, _cities in VE_STATE_CITIES:
        urls.append((f"/estados/{_sslug}", "0.8"))
    for slug, _city, _state in CITY_PAGES:
        urls.append((f"/carros/{slug}", "0.8"))
    for post in BLOG_POSTS:
        urls.append((f"/blog/{post['slug']}", "0.6"))
    # Nunca se indexan carros demo.
    for l in browse_listings(limit=1000, include_demo=False):
        urls.append((f"/carro/{listing_slug(l)}", "0.7"))
    items = "\n".join(
        f"  <url><loc>{base}{path}</loc><changefreq>daily</changefreq>"
        f"<priority>{prio}</priority></url>"
        for path, prio in urls
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}\n</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


def _listing_page(request: Request, listing: dict):
    user = me(request)
    if int(listing.get("is_demo") or 0) and not _show_demo() and not _admin(request):
        resp = _page(request, "listing_missing.html", listing_id=listing["id"])
        resp.status_code = 404
        return resp
    if listing.get("status") == "pending_pay":
        owner = bool(user and int(user["id"]) == int(listing["user_id"]))
        if not owner and not _admin(request):
            return _page(request, "listing_missing.html", listing_id=listing["id"])
    seller = get_user(listing["user_id"])
    rep = seller_reputation(listing["user_id"]) if listing.get("user_id") else {}
    return _page(
        request, "listing.html", listing=listing, seller=seller, reported=False,
        share=_share(request, listing), reputation=rep,
        canonical=listing_canonical_url(_public_base(request), listing),
    )


@app.get("/carro/{slug}", response_class=HTMLResponse)
def listing_detail_slug(request: Request, slug: str):
    m = re.search(r"-(\d+)$", slug or "")
    listing_id = int(m.group(1)) if m else 0
    listing = get_listing(listing_id) if listing_id else None
    if not listing:
        return _page(request, "listing_missing.html", listing_id=listing_id)
    if slug != listing_slug(listing):
        return RedirectResponse(
            listing_canonical_url(_public_base(request), listing), status_code=301
        )
    return _listing_page(request, listing)


@app.get("/listing/{listing_id}", response_class=HTMLResponse)
def listing_detail(request: Request, listing_id: int):
    listing = get_listing(listing_id)
    if not listing:
        return _page(request, "listing_missing.html", listing_id=listing_id)
    # URL vieja -> 301 a la URL con slug (SEO)
    return RedirectResponse(
        listing_canonical_url(_public_base(request), listing), status_code=301
    )
# ------------------------------------------------------------ fin SEO duro


def _fulfill_publish(listing: dict, sess) -> tuple[bool, str]:
    """Activa el anuncio si la sesión de Stripe es EXACTAMENTE su pago de publicación."""
    lid = int(listing["id"])
    ok, why = stripe_pay.verify_paid_session(
        sess,
        kind=stripe_pay.KIND_PUBLISH,
        target_id=lid,
        expected_cents=int(listing.get("publish_cents") or 0),
        stored_session_id=listing.get("stripe_publish_session") or "",
    )
    if not ok:
        return False, why
    ok, _new = claim_stripe_session(str(stripe_pay._get(sess, "id")), stripe_pay.KIND_PUBLISH, lid)
    if not ok:
        return False, "ese pago ya se usó"
    if listing.get("status") == "pending_pay":
        update_listing(lid, status="active", publish_paid=1)
    return True, "ok"


def _fulfill_commission(deal: dict, sess) -> tuple[bool, str, bool]:
    """Marca la venta pagada si la sesión es EXACTAMENTE su comisión. (ok, motivo, nueva)."""
    did = int(deal["id"])
    ok, why = stripe_pay.verify_paid_session(
        sess,
        kind=stripe_pay.KIND_COMMISSION,
        target_id=did,
        expected_cents=stripe_pay.amount_cents(int(deal.get("commission") or 0)),
        stored_session_id=deal.get("stripe_session_id") or "",
    )
    if not ok:
        return False, why, False
    ok, new = claim_stripe_session(str(stripe_pay._get(sess, "id")), stripe_pay.KIND_COMMISSION, did)
    if not ok:
        return False, "ese pago ya se usó", False
    first = deal.get("status") != "paid"
    if first:
        confirm_deal_paid(did, pay_method="stripe")
        add_chat_message(
            int(deal["conversation_id"]), int(deal["seller_id"]),
            f"Comisión de ${deal['commission']} pagada con Stripe. Venta cerrada.",
        )
    return True, "ok", first


@app.post("/listing/{listing_id}/pagar-publicar")
def listing_pay_publish(request: Request, listing_id: int):
    user = me(request)
    listing = get_listing(listing_id)
    if not listing or not user or int(user["id"]) != int(listing["user_id"]):
        return RedirectResponse("/login", status_code=302)
    if listing.get("status") != "pending_pay":
        return RedirectResponse(f"/listing/{listing_id}", status_code=303)
    if not stripe_enabled():
        return listing_detail(request, listing_id)
    fee = _publish_fee()
    base = _public_base(request)
    try:
        sess = stripe_pay.create_publish_checkout(
            amount_usd=fee,
            listing_id=listing_id,
            title=listing.get("title") or "",
            success_url=f"{base}/listing/{listing_id}/publicado-ok?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/listing/{listing_id}",
        )
    except Exception as e:
        print(f"[stripe] checkout publicar falló: {type(e).__name__}")
        return _page(
            request, "listing.html", listing=listing,
            seller=get_user(listing["user_id"]),
            error="No se pudo abrir Stripe. Intenta de nuevo.",
            share=_share(request, listing),
        )
    update_listing(
        listing_id, stripe_publish_session=sess["id"], publish_cents=sess["amount_cents"]
    )
    return RedirectResponse(sess["url"], status_code=303)


@app.get("/listing/{listing_id}/publicado-ok")
def listing_publish_ok(request: Request, listing_id: int, session_id: str = ""):
    user = me(request)
    listing = get_listing(listing_id)
    if not listing or not user or int(user["id"]) != int(listing["user_id"]):
        return RedirectResponse("/login", status_code=302)
    sid = (session_id or "").strip()
    if not sid or sid != (listing.get("stripe_publish_session") or ""):
        return RedirectResponse(f"/listing/{listing_id}", status_code=303)
    try:
        sess = stripe_pay.retrieve_session(sid)
    except Exception:
        return listing_detail(request, listing_id)
    ok, why = _fulfill_publish(listing, sess)
    if not ok:
        print(f"[stripe] publicar {listing_id} rechazado: {why}")
    return RedirectResponse(f"/listing/{listing_id}", status_code=303)


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Webhook de Stripe (firma verificada con STRIPE_WEBHOOK_SECRET)."""
    if not stripe_webhook_secret():
        return JSONResponse({"ok": False, "error": "webhook no configurado"}, status_code=503)
    payload = await request.body()
    try:
        event = stripe_pay.construct_webhook_event(
            payload, request.headers.get("stripe-signature") or ""
        )
    except Exception:
        return JSONResponse({"ok": False, "error": "firma inválida"}, status_code=400)
    etype = str(stripe_pay._get(event, "type") or "")
    if etype not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return {"ok": True, "ignored": etype}
    data = stripe_pay._get(event, "data") or {}
    sess = stripe_pay._get(data, "object")
    meta = stripe_pay.session_metadata(sess)
    if meta.get("app") != stripe_pay.APP_TAG:
        return {"ok": True, "ignored": "otra app"}
    kind = meta.get("kind")
    try:
        if kind == stripe_pay.KIND_PUBLISH:
            listing = get_listing(int(meta.get("listing_id") or 0))
            if not listing:
                return {"ok": True, "ignored": "anuncio no existe"}
            ok, why = _fulfill_publish(listing, sess)
        elif kind == stripe_pay.KIND_COMMISSION:
            deal = get_deal(int(meta.get("deal_id") or 0))
            if not deal:
                return {"ok": True, "ignored": "venta no existe"}
            ok, why, _ = _fulfill_commission(deal, sess)
        else:
            return {"ok": True, "ignored": "tipo desconocido"}
    except (TypeError, ValueError):
        return {"ok": True, "ignored": "metadata inválida"}
    if not ok:
        print(f"[stripe] webhook {kind} rechazado: {why}")
    return {"ok": True, "applied": ok}


@app.post("/listing/{listing_id}/comprobante-publicar")
async def listing_publish_proof(request: Request, listing_id: int, proof: UploadFile = File(None)):
    user = me(request)
    listing = get_listing(listing_id)
    if not listing or not user or int(user["id"]) != int(listing["user_id"]):
        return RedirectResponse("/login", status_code=302)
    if listing.get("status") != "pending_pay":
        return RedirectResponse(f"/listing/{listing_id}", status_code=303)
    try:
        path = await _save_photo(listing_id, proof, private=True)
    except ValueError as e:
        path = ""
        err = str(e)
    else:
        err = "Sube una foto o captura del pago de publicación"
    if not path:
        return _page(
            request, "listing.html", listing=listing,
            seller=get_user(listing["user_id"]),
            error=err,
            share=_share(request, listing),
        )
    update_listing(listing_id, publish_proof=path)
    return RedirectResponse(f"/listing/{listing_id}", status_code=303)


@app.post("/listing/{listing_id}/reportar")
def reportar_listing(
    request: Request,
    listing_id: int,
    reason: str = Form(...),
    detail: str = Form(""),
):
    listing = get_listing(listing_id)
    if not listing:
        return RedirectResponse("/", status_code=302)
    user = me(request)
    ip = client_ip(request)
    if not rl_allow("report_ip", ip) or not rl_allow("report_listing_ip", f"{ip}:{listing_id}"):
        resp = _page(
            request, "listing.html", listing=listing, seller=get_user(listing["user_id"]),
            reported=True, share=_share(request, listing),
            reputation=seller_reputation(listing["user_id"]) if listing.get("user_id") else {},
        )
        resp.status_code = 429
        return resp
    add_report(
        listing_id,
        reason=reason,
        detail=detail,
        reporter_id=int(user["id"]) if user else 0,
    )
    seller = get_user(listing["user_id"])
    return _page(
        request, "listing.html", listing=listing, seller=seller, reported=True,
        share=_share(request, listing),
        reputation=seller_reputation(listing["user_id"]) if listing.get("user_id") else {},
    )


@app.get("/chat/{listing_id}")
def chat_start(request: Request, listing_id: int):
    user = me(request)
    if not user:
        return RedirectResponse(f"/login?next=/chat/{listing_id}", status_code=302)
    listing = get_listing(listing_id)
    if (
        not listing
        or listing.get("status") == "pending_pay"
        or (int(listing.get("is_demo") or 0) and not _show_demo())
    ):
        return _page(request, "listing_missing.html", listing_id=listing_id)
    if int(user["id"]) == int(listing["user_id"]):
        return RedirectResponse("/mensajes", status_code=302)
    try:
        convo = get_or_create_conversation(listing_id, user["id"], listing["user_id"])
    except ValueError as e:
        return _page(request, "listing.html", listing=listing, seller=get_user(listing["user_id"]), error=str(e))
    return RedirectResponse(f"/c/{convo['id']}", status_code=302)


@app.get("/api/c/{cid}/mensajes")
def api_chat_messages(request: Request, cid: int, after: int = 0):
    user = me(request)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    convo = get_conversation(cid)
    if not convo or int(user["id"]) not in (int(convo["buyer_id"]), int(convo["seller_id"])):
        return JSONResponse({"ok": False}, status_code=403)
    msgs = [m for m in list_chat_messages(cid) if int(m["id"]) > int(after or 0)]
    mark_conversation_read(cid, user["id"])
    return {"ok": True, "messages": msgs, "me_id": user["id"]}


@app.post("/api/c/{cid}/mensaje")
def api_chat_send(request: Request, cid: int, body: str = Form(...)):
    user = me(request)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    if not _chat_allowed(user):
        return JSONResponse(
            {"ok": False, "error": "Vas muy rápido. Espera un momento."}, status_code=429
        )
    try:
        msg = add_chat_message(cid, user["id"], body)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    convo = get_conversation(cid)
    if convo:
        other_id = convo["seller_id"] if int(user["id"]) == int(convo["buyer_id"]) else convo["buyer_id"]
        other = get_user(other_id)
        listing = get_listing(convo["listing_id"])
        if (
            other and other.get("email")
            and not str(other.get("email") or "").endswith("@demo.motorcriollo")
            and rl_allow("chat_mail", f"{cid}:{other_id}")
        ):
            _queue_mail(
                send_chat_notice,
                other["email"],
                other.get("name") or "hola",
                (listing or {}).get("title") or "un carro",
                (body or "")[:240],
                cid,
            )
    return {"ok": True, "message": msg}


@app.post("/favorito/{listing_id}")
def fav_toggle(request: Request, listing_id: int):
    user = me(request)
    if not user:
        return RedirectResponse(f"/login?next=/listing/{listing_id}", status_code=302)
    toggle_favorite(user["id"], listing_id)
    ref = request.headers.get("referer") or ""
    if "/favoritos" in ref:
        return RedirectResponse("/favoritos", status_code=303)
    if f"/listing/{listing_id}" in ref:
        return RedirectResponse(f"/listing/{listing_id}", status_code=303)
    return RedirectResponse("/#publicaciones", status_code=303)


@app.get("/favoritos", response_class=HTMLResponse)
def favs_page(request: Request):
    user = me(request)
    if not user:
        return RedirectResponse("/login?next=/favoritos", status_code=302)
    return _page(request, "favoritos.html", listings=list_favorites(user["id"]))


@app.get("/carros/{slug}", response_class=HTMLResponse)
def city_page(request: Request, slug: str):
    found = next((c for c in CITY_PAGES if c[0] == slug), None)
    if not found:
        return RedirectResponse("/#publicaciones", status_code=302)
    _slug, city, state = found
    show_demo = _show_demo()
    listings = browse_listings(city=city, include_demo=show_demo, limit=60)
    state_slug = next((s[0] for s in VE_STATE_CITIES if s[1] == state), "")
    return _page(
        request, "ciudad.html",
        city=city, state=state, slug=slug, state_slug=state_slug, listings=listings,
        total=len(listings),
    )


@app.get("/estados/{state_slug}", response_class=HTMLResponse)
def estado_page(request: Request, state_slug: str):
    found = next((s for s in VE_STATE_CITIES if s[0] == state_slug), None)
    if not found:
        return RedirectResponse("/#publicaciones", status_code=302)
    _sslug, state, cities = found
    show_demo = _show_demo()
    listings = browse_listings(state=state, include_demo=show_demo, limit=60)
    base = _public_base(request)
    return _page(
        request, "estado.html",
        state=state, state_slug=state_slug, cities=cities,
        listings=listings, total=len(listings),
        canonical=f"{base}/estados/{state_slug}",
    )


@app.get("/blog", response_class=HTMLResponse)
def blog_index(request: Request):
    base = _public_base(request)
    return _page(request, "blog_index.html", posts=BLOG_POSTS, canonical=f"{base}/blog")


@app.get("/blog/{slug}", response_class=HTMLResponse)
def blog_post(request: Request, slug: str):
    post = next((p for p in BLOG_POSTS if p["slug"] == slug), None)
    if not post:
        return RedirectResponse("/blog", status_code=302)
    base = _public_base(request)
    return _page(
        request, "blog_post.html", post=post,
        canonical=f"{base}/blog/{post['slug']}",
    )


@app.get("/c/{cid}", response_class=HTMLResponse)
def chat_view(request: Request, cid: int, error: str = ""):
    user = me(request)
    if not user:
        return RedirectResponse("/login?next=/mensajes", status_code=302)
    convo = get_conversation(cid)
    if not convo or int(user["id"]) not in (int(convo["buyer_id"]), int(convo["seller_id"])):
        return RedirectResponse("/mensajes", status_code=302)
    listing = get_listing(convo["listing_id"])
    other_id = convo["seller_id"] if int(user["id"]) == int(convo["buyer_id"]) else convo["buyer_id"]
    deal = get_deal_by_conversation(cid)
    mark_conversation_read(cid, user["id"])
    return _page(
        request,
        "chat.html",
        convo=convo,
        listing=listing,
        other=get_user(other_id),
        messages=list_chat_messages(cid),
        deal=deal,
        i_am_seller=int(user["id"]) == int(convo["seller_id"]),
        can_rate=bool(
            deal
            and deal.get("status") == "paid"
            and int(user["id"]) == int(convo["buyer_id"])
            and not has_rated_deal(deal["id"])
        ),
        error=error,
    )


@app.post("/c/{cid}/mensaje")
def chat_send(request: Request, cid: int, body: str = Form(...)):
    user = me(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not _chat_allowed(user):
        return chat_view(request, cid, error="Vas muy rápido. Espera un momento.")
    try:
        add_chat_message(cid, user["id"], body)
    except ValueError:
        return RedirectResponse(f"/c/{cid}", status_code=303)
    convo = get_conversation(cid)
    if convo:
        other_id = convo["seller_id"] if int(user["id"]) == int(convo["buyer_id"]) else convo["buyer_id"]
        other = get_user(other_id)
        listing = get_listing(convo["listing_id"])
        if (
            other and other.get("email")
            and not str(other.get("email") or "").endswith("@demo.motorcriollo")
            and rl_allow("chat_mail", f"{cid}:{other_id}")
        ):
            _queue_mail(
                send_chat_notice,
                other["email"],
                other.get("name") or "hola",
                (listing or {}).get("title") or "un carro",
                (body or "")[:240],
                cid,
            )
    return RedirectResponse(f"/c/{cid}", status_code=303)


@app.post("/c/{cid}/aceptar")
def chat_accept(request: Request, cid: int):
    user = me(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    try:
        fee = _commission()
        accept_deal(cid, user["id"], fee)
        add_chat_message(
            cid, user["id"],
            f"Acepté la venta. Debo pagar ${fee} de comisión a MotorCriollo para cerrar.",
        )
    except ValueError as e:
        return chat_view(request, cid, error=str(e))
    return RedirectResponse(f"/c/{cid}", status_code=303)


@app.post("/c/{cid}/comprobante")
async def chat_proof(request: Request, cid: int, proof: UploadFile = File(None)):
    user = me(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    convo = get_conversation(cid)
    deal = get_deal_by_conversation(cid)
    if not convo or not deal or int(user["id"]) != int(convo["seller_id"]):
        return RedirectResponse("/mensajes", status_code=302)
    try:
        path = await _save_photo(deal["listing_id"], proof, private=True)
    except ValueError as e:
        return chat_view(request, cid, error=str(e))
    if not path:
        return chat_view(request, cid, error="Sube una foto o captura del pago")
    set_deal_proof(deal["id"], path)
    add_chat_message(cid, user["id"], "Subí el comprobante de la comisión. Administración lo revisa.")
    return RedirectResponse(f"/c/{cid}", status_code=303)


def _public_base(request: Request) -> str:
    base = (PUBLIC_BASE_URL or str(request.base_url).rstrip("/")).rstrip("/")
    if base.startswith("https://www.motorcriollo.store"):
        base = "https://motorcriollo.store"
    return base


@app.post("/c/{cid}/pagar-stripe")
def chat_pay_stripe(request: Request, cid: int):
    user = me(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not stripe_enabled():
        return chat_view(request, cid, error="Stripe no está configurado todavía")
    convo = get_conversation(cid)
    deal = get_deal_by_conversation(cid)
    if not convo or not deal or int(user["id"]) != int(convo["seller_id"]):
        return RedirectResponse("/mensajes", status_code=302)
    if deal.get("status") not in ("accepted", "proof"):
        return RedirectResponse(f"/c/{cid}", status_code=303)
    listing = get_listing(convo["listing_id"]) or {}
    base = _public_base(request)
    try:
        sess = stripe_pay.create_commission_checkout(
            amount_usd=int(deal["commission"]),
            deal_id=int(deal["id"]),
            conversation_id=cid,
            title=listing.get("title") or "venta",
            success_url=f"{base}/c/{cid}/pago-ok?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/c/{cid}?pago=0",
        )
    except Exception as e:
        print(f"[stripe] checkout comisión falló: {type(e).__name__}")
        return chat_view(request, cid, error="No se pudo abrir Stripe. Intenta de nuevo.")
    set_deal_stripe_session(deal["id"], sess["id"])
    return RedirectResponse(sess["url"], status_code=303)


@app.get("/c/{cid}/pago-ok")
def chat_pay_ok(request: Request, cid: int, session_id: str = ""):
    user = me(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    convo = get_conversation(cid)
    deal = get_deal_by_conversation(cid)
    if not convo or not deal or int(user["id"]) not in (
        int(convo["buyer_id"]),
        int(convo["seller_id"]),
    ):
        return RedirectResponse("/mensajes", status_code=302)
    sid = (session_id or "").strip()
    if not sid:
        return chat_view(request, cid, error="Falta el pago de Stripe")
    if sid != (deal.get("stripe_session_id") or ""):
        return chat_view(request, cid, error="Ese pago no corresponde a esta venta")
    try:
        sess = stripe_pay.retrieve_session(sid)
    except Exception:
        return chat_view(request, cid, error="No se pudo verificar el pago")
    ok, why, _first = _fulfill_commission(deal, sess)
    if not ok:
        print(f"[stripe] comisión deal {deal['id']} rechazada: {why}")
        return chat_view(request, cid, error="El pago no está confirmado o no corresponde a esta venta")
    return RedirectResponse(f"/c/{cid}", status_code=303)


@app.post("/c/{cid}/calificar")
def chat_rate(request: Request, cid: int, stars: int = Form(...), comment: str = Form("")):
    user = me(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    convo = get_conversation(cid)
    deal = get_deal_by_conversation(cid)
    if not convo or not deal or deal.get("status") != "paid":
        return RedirectResponse(f"/c/{cid}", status_code=302)
    if int(user["id"]) != int(deal["buyer_id"]):
        return RedirectResponse(f"/c/{cid}", status_code=302)
    try:
        add_rating(
            seller_id=deal["seller_id"],
            buyer_id=user["id"],
            stars=stars,
            comment=comment,
            deal_id=deal["id"],
            listing_id=deal["listing_id"],
        )
        add_chat_message(cid, user["id"], f"Califiqué al vendedor: {int(stars)}/5.")
    except ValueError as e:
        return chat_view(request, cid, error=str(e))
    return RedirectResponse(f"/c/{cid}", status_code=303)


@app.get("/vendedor/{user_id}", response_class=HTMLResponse)
def seller_profile(request: Request, user_id: int):
    seller = get_user(user_id)
    if not seller:
        return RedirectResponse("/#publicaciones", status_code=302)
    return _page(
        request,
        "vendedor.html",
        seller=seller,
        reputation=seller_reputation(user_id),
        listings=list_user_listings(user_id),
    )


# ----------------------------------------------------------- publicar ----

@app.get("/publicar", response_class=HTMLResponse)
def publicar_get(request: Request):
    user = me(request)
    if not user:
        return RedirectResponse("/login?next=/publicar", status_code=302)
    if not can_publish(user):
        return RedirectResponse("/verificacion", status_code=302)
    return _page(request, "publicar.html", listing=None)


@app.post("/publicar")
async def publicar_post(
    request: Request,
    title: str = Form(...),
    brand: str = Form(...),
    model: str = Form(...),
    year: int = Form(...),
    price: int = Form(...),
    mileage: int = Form(0),
    transmission: str = Form(""),
    fuel_type: str = Form(""),
    condition: str = Form(""),
    description: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    phone: str = Form(""),
    photos: list[UploadFile] = File(default=[]),
    photo_odometer: UploadFile = File(None),
    photo_serial: UploadFile = File(None),
    photo_title: UploadFile = File(None),
):
    user = me(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not can_publish(user):
        return RedirectResponse("/verificacion", status_code=302)
    if not (phone or user.get("phone")):
        return _page(request, "publicar.html", listing=None, error="Pon un WhatsApp activo")
    try:
        listing = create_listing(
            user_id=user["id"], title=title, brand=brand, model=model, year=year,
            price=price, mileage=mileage, transmission=transmission, fuel_type=fuel_type,
            condition=condition, description=description, city=city, state=state,
            phone=phone or user.get("phone") or "",
        )
        await _save_listing_photos(listing["id"], photos)
        odo = await _save_photo(listing["id"], photo_odometer)
        ser = await _save_photo(listing["id"], photo_serial, private=True)
        tit = await _save_photo(listing["id"], photo_title, private=True)
        if not (odo and ser and tit):
            return _page(
                request, "publicar.html", listing=listing,
                error="Sube odómetro, serial y título (puedes tapar datos sensibles).",
            )
        update_listing(listing["id"], photo_odometer=odo, photo_serial=ser, photo_title=tit)
    except ValueError as e:
        return _page(request, "publicar.html", listing=None, error=str(e))
    return RedirectResponse(f"/listing/{listing['id']}", status_code=303)


@app.get("/listing/{listing_id}/editar", response_class=HTMLResponse)
def editar_get(request: Request, listing_id: int):
    user = me(request)
    listing = get_listing(listing_id)
    if not listing:
        return RedirectResponse("/", status_code=302)
    if not user or user["id"] != listing["user_id"]:
        return RedirectResponse("/login", status_code=302)
    return _page(request, "publicar.html", listing=listing)


@app.post("/listing/{listing_id}/editar")
async def editar_post(
    request: Request,
    listing_id: int,
    title: str = Form(...),
    brand: str = Form(...),
    model: str = Form(...),
    year: int = Form(...),
    price: int = Form(...),
    mileage: int = Form(0),
    transmission: str = Form(""),
    fuel_type: str = Form(""),
    condition: str = Form(""),
    description: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    phone: str = Form(""),
    photos: list[UploadFile] = File(default=[]),
    photo_odometer: UploadFile = File(None),
    photo_serial: UploadFile = File(None),
    photo_title: UploadFile = File(None),
):
    user = me(request)
    listing = get_listing(listing_id)
    if not listing:
        return RedirectResponse("/", status_code=302)
    if not user or user["id"] != listing["user_id"]:
        return RedirectResponse("/login", status_code=302)
    try:
        listing = update_listing(
            listing_id, title=title, brand=brand, model=model, year=year, price=price,
            mileage=mileage, transmission=transmission, fuel_type=fuel_type,
            condition=condition, description=description, city=city, state=state, phone=phone,
        )
        await _save_listing_photos(listing_id, photos)
        docs = {}
        odo = await _save_photo(listing_id, photo_odometer)
        ser = await _save_photo(listing_id, photo_serial, private=True)
        tit = await _save_photo(listing_id, photo_title, private=True)
        if odo:
            docs["photo_odometer"] = odo
        if ser:
            docs["photo_serial"] = ser
        if tit:
            docs["photo_title"] = tit
        if docs:
            listing = update_listing(listing_id, **docs)
    except ValueError as e:
        return _page(request, "publicar.html", listing=listing, error=str(e))
    return RedirectResponse(f"/listing/{listing_id}", status_code=303)


@app.post("/listing/{listing_id}/estado")
def cambiar_estado(request: Request, listing_id: int, status: str = Form(...)):
    user = me(request)
    listing = get_listing(listing_id)
    if not listing or not user or user["id"] != listing["user_id"]:
        return RedirectResponse("/login", status_code=302)
    if status == "active" and listing.get("status") == "pending_pay" and not int(listing.get("publish_paid") or 0):
        return RedirectResponse("/mis-publicaciones", status_code=303)
    if status in ("active", "sold", "inactive"):
        update_listing(listing_id, status=status)
    return RedirectResponse("/mis-publicaciones", status_code=303)


@app.post("/listing/{listing_id}/eliminar")
def eliminar_listing(request: Request, listing_id: int):
    user = me(request)
    listing = get_listing(listing_id)
    if not listing or not user or user["id"] != listing["user_id"]:
        return RedirectResponse("/login", status_code=302)
    files = listing_file_paths(listing_id)
    delete_listing(listing_id)
    _remove_files(files)
    return RedirectResponse("/mis-publicaciones", status_code=303)


@app.get("/mis-publicaciones", response_class=HTMLResponse)
def mis_publicaciones(request: Request):
    user = me(request)
    if not user:
        return RedirectResponse("/login?next=/mis-publicaciones", status_code=302)
    listings = list_user_listings(user["id"])
    return _page(request, "mis_publicaciones.html", listings=listings)


@app.get("/verificacion", response_class=HTMLResponse)
def verificacion_get(request: Request, ok: int = 0):
    user = me(request)
    if not user:
        return RedirectResponse("/login?next=/verificacion", status_code=302)
    return _page(request, "verificacion.html", sent=bool(ok))


@app.post("/verificacion")
async def verificacion_post(
    request: Request,
    full_name: str = Form(...),
    id_number: str = Form(...),
    address: str = Form(...),
    city: str = Form(""),
    state: str = Form(""),
    id_photo: UploadFile = File(None),
    address_photo: UploadFile = File(None),
):
    user = me(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.get("kyc_status") == "approved":
        return RedirectResponse("/publicar", status_code=302)
    try:
        id_path = await _save_kyc_photo(user["id"], "id", id_photo)
        addr_path = await _save_kyc_photo(user["id"], "addr", address_photo)
        submit_kyc(
            user["id"],
            full_name=full_name,
            id_number=id_number,
            address=address,
            city=city or user.get("city") or "",
            state=state or user.get("state") or "",
            id_photo=id_path,
            address_photo=addr_path,
        )
    except ValueError as e:
        return _page(request, "verificacion.html", error=str(e))
    return RedirectResponse("/verificacion?ok=1", status_code=303)


@app.get("/mensajes", response_class=HTMLResponse)
def mensajes(request: Request):
    user = me(request)
    if not user:
        return RedirectResponse("/login?next=/mensajes", status_code=302)
    return _page(request, "mensajes.html", convos=list_conversations(user["id"]))


# --------------------------------------------------------------- auth ----

@app.get("/registro", response_class=HTMLResponse)
def registro_get(request: Request, next: str = ""):
    if me(request):
        return RedirectResponse(_safe_next(next), status_code=302)
    return _page(request, "registro.html", next=next)


@app.post("/registro")
def registro_post(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    phone: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    next: str = Form(""),
):
    if not rl_allow("signup_ip", client_ip(request)):
        return _too_many(request, "registro.html", next=next)
    try:
        user = create_user(
            email=email, password=password, name=name, phone=phone, city=city, state=state,
        )
        _queue_verify_email(user)
        _queue_welcome_email(user)
    except ValueError as e:
        return _page(request, "registro.html", error=str(e), next=next)
    token = create_session(user["id"], SESSION_DAYS)
    resp = RedirectResponse(_safe_next(next), status_code=303)
    return _set_session(resp, token)


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request, next: str = ""):
    if me(request):
        return RedirectResponse(_safe_next(next), status_code=302)
    return _page(request, "login.html", next=next)


@app.post("/login")
def login_post(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("")):
    em = (email or "").strip().lower()[:254]
    if not rl_allow("login_ip", client_ip(request)) or not rl_allow("login_email", em):
        return _too_many(request, "login.html", next=next)
    user = login(email, password)
    if not user:
        return _page(request, "login.html", error="Email o contraseña incorrectos", next=next)
    token = create_session(user["id"], SESSION_DAYS)
    resp = RedirectResponse(_safe_next(next), status_code=303)
    return _set_session(resp, token)


@app.get("/terminos", response_class=HTMLResponse)
def terminos(request: Request):
    return _page(request, "terminos.html")


@app.get("/privacidad", response_class=HTMLResponse)
def privacidad(request: Request):
    return _page(request, "privacidad.html")


@app.get("/salir", response_class=HTMLResponse)
def salir_get(request: Request):
    # GET ya no cierra sesión (evita CSRF por enlace); muestra el botón.
    if not me(request):
        return RedirectResponse("/", status_code=302)
    return _page(request, "salir.html")


@app.post("/salir")
def salir(request: Request):
    delete_session(request.cookies.get(SESSION_COOKIE))
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get("/auth/google")
def auth_google(request: Request, next: str = ""):
    if not google_enabled():
        return _page(
            request, "login.html",
            error="El inicio de sesión con Google no está disponible ahora.",
        )
    state = secrets.token_urlsafe(24)
    url = google_authorize_url(f"{_base(request)}/auth/google/callback", state)
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax")
    resp.set_cookie(
        OAUTH_NEXT_COOKIE, _safe_next(next), max_age=600, httponly=True, samesite="lax"
    )
    return resp


@app.get("/auth/google/callback")
def auth_google_cb(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return _page(request, "login.html", error="Google canceló o rechazó el inicio de sesión.")
    saved = request.cookies.get(OAUTH_STATE_COOKIE)
    if not code or not saved or saved != state:
        return _page(request, "login.html", error="Sesión de Google inválida. Intenta de nuevo.")
    try:
        info = google_user(code, f"{_base(request)}/auth/google/callback")
        user, is_new = upsert_oauth_user(
            email=info["email"], name=info["name"], provider="google", oauth_id=info["oauth_id"],
        )
    except UnverifiedAccountError as e:
        return _page(request, "login.html", error=str(e))
    except Exception as e:
        print(f"[oauth] google falló: {type(e).__name__}")
        return _page(request, "login.html", error="No se pudo entrar con Google. Intenta de nuevo.")
    return _finish_oauth(request, user, is_new)


@app.get("/auth/apple")
def auth_apple(request: Request):
    if not apple_enabled():
        return _page(
            request, "login.html",
            error="El inicio de sesión con Apple no está disponible.",
        )
    state = secrets.token_urlsafe(24)
    url = apple_authorize_url(f"{_base(request)}/auth/apple/callback", state)
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax")
    return resp


@app.post("/auth/apple/callback")
async def auth_apple_cb(request: Request):
    form = await request.form()
    code = str(form.get("code") or "")
    state = str(form.get("state") or "")
    user_json = str(form.get("user") or "")
    err = str(form.get("error") or "")
    if err:
        return _page(request, "login.html", error="Apple canceló o rechazó el inicio de sesión.")
    saved = request.cookies.get(OAUTH_STATE_COOKIE)
    if not code or not saved or saved != state:
        return _page(request, "login.html", error="Sesión de Apple inválida. Intenta de nuevo.")
    try:
        info = apple_user(code, f"{_base(request)}/auth/apple/callback", user_json)
        user, is_new = upsert_oauth_user(
            email=info["email"], name=info["name"], provider="apple", oauth_id=info["oauth_id"],
        )
    except UnverifiedAccountError as e:
        return _page(request, "login.html", error=str(e))
    except Exception as e:
        print(f"[oauth] apple falló: {type(e).__name__}")
        return _page(request, "login.html", error="No se pudo entrar con Apple. Intenta de nuevo.")
    return _finish_oauth(request, user, is_new)


@app.get("/verificar")
def verificar(request: Request, token: str = ""):
    uid = take_email_token(token, "verify")
    if not uid:
        return _page(request, "login.html", error="El enlace no vale o ya se usó.")
    update_profile(uid, email_verified=1)
    user = get_user(uid)
    if not user:
        return RedirectResponse("/login", status_code=302)
    tok = create_session(user["id"], SESSION_DAYS)
    resp = RedirectResponse("/", status_code=303)
    return _set_session(resp, tok)


@app.post("/correo/reenviar")
def correo_reenviar(request: Request):
    user = me(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if rl_allow("verify_mail_user", str(user["id"])):
        _queue_verify_email(user)
    return RedirectResponse("/mis-publicaciones", status_code=303)


@app.get("/olvide", response_class=HTMLResponse)
def olvide_get(request: Request):
    return _page(request, "olvide.html")


@app.post("/olvide")
def olvide_post(request: Request, email: str = Form(...)):
    em = (email or "").strip().lower()[:254]
    if not rl_allow("forgot_ip", client_ip(request)):
        return _too_many(request, "olvide.html")
    row = get_user_by_email(em) if rl_allow("forgot_email", em) else None
    if row and int(getv_row(row, "is_demo") or 0):
        row = None
    if row:
        uid = row["id"] if not isinstance(row, dict) else row.get("id")
        user = get_user(uid)
        if user and email_ready():
            tok = make_email_token(uid, "reset", 2)

            def _run():
                send_reset(user["email"], user.get("name") or "", tok)

            threading.Thread(target=_run, name="mc-mail-reset", daemon=True).start()
    return _page(request, "olvide.html", sent=True)


@app.get("/reset", response_class=HTMLResponse)
def reset_get(request: Request, token: str = ""):
    if not token:
        return RedirectResponse("/olvide", status_code=302)
    return _page(request, "reset.html", token=token)


@app.post("/reset")
def reset_post(request: Request, token: str = Form(...), password: str = Form(...)):
    if len(password or "") < PASSWORD_MIN_LEN:
        return _page(
            request, "reset.html", token=token,
            error=f"La contraseña debe tener al menos {PASSWORD_MIN_LEN} caracteres",
        )
    uid = take_email_token(token, "reset")
    if not uid:
        return _page(request, "olvide.html", error="El enlace no vale o ya se usó.")
    try:
        set_password(uid, password)  # también cierra todas las sesiones del usuario
    except ValueError as e:
        # El token ya se consumió: hay que pedir otro enlace.
        return _page(request, "olvide.html", error=f"{e}. Pide un enlace nuevo.")
    update_profile(uid, email_verified=1)
    return _page(request, "login.html", info="ok")


@app.post("/eliminar-cuenta")
def eliminar_cuenta(request: Request):
    user = me(request)
    if not user:
        return RedirectResponse("/", status_code=302)
    files = user_file_paths(user["id"])
    delete_user(user["id"])
    _remove_files(files)
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


def getv_row(row, key):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except Exception:
        return None


def _require_admin(request: Request):
    if _admin(request):
        return None
    return RedirectResponse("/admin/entrar", status_code=302)


@app.get("/admin/entrar", response_class=HTMLResponse)
def admin_login_get(request: Request):
    if _admin(request):
        return RedirectResponse("/admin", status_code=302)
    return _page(request, "admin_login.html")


@app.post("/admin/entrar")
def admin_login_post(request: Request, password: str = Form(...)):
    ip = client_ip(request)
    if rl_blocked("admin_ip", ip) or rl_blocked("admin_global", "all"):
        return _too_many(request, "admin_login.html", "Panel bloqueado por intentos fallidos. Espera 15 minutos.")
    want = admin_password()
    if not want:
        return _page(request, "admin_login.html", error="El panel está cerrado: falta configurar MOTORCRIOLLO_ADMIN (12+ caracteres).")
    if not hmac.compare_digest((password or "").encode("utf-8"), want.encode("utf-8")):
        rl_allow("admin_ip", ip)
        rl_allow("admin_global", "all")
        return _page(request, "admin_login.html", error="Clave incorrecta")
    limiter.reset(f"admin_ip:{ip}")
    token = create_admin_session(7)
    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie(
        ADMIN_COOKIE,
        token,
        max_age=7 * 86400,
        httponly=True,
        samesite="lax",
        secure=bool(os.environ.get("RENDER") or PUBLIC_BASE_URL.startswith("https")),
    )
    return resp


@app.post("/admin/salir")
def admin_logout(request: Request):
    delete_admin_session(request.cookies.get(ADMIN_COOKIE))
    resp = RedirectResponse("/admin/entrar", status_code=303)
    resp.delete_cookie(ADMIN_COOKIE)
    return resp


@app.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request, tab: str = "kyc"):
    gate = _require_admin(request)
    if gate:
        return gate
    pending = list_kyc("pending")
    reviewed = list_kyc("all")
    return _page(
        request,
        "admin.html",
        tab=tab or "kyc",
        stats={
            "listings": count_active_listings(),
            "users": count_users(),
            "kyc_pending": count_kyc_pending(),
            "deals_open": count_deals_open(),
            "reports_open": count_reports_open(),
        },
        pending=pending,
        reviewed=[u for u in reviewed if u.get("kyc_status") != "pending"],
        users=list_users_admin(),
        listings=list_all_listings(),
        deals=list_deals(),
        reports=list_reports("open"),
        settings={
            "commission": str(_commission()),
            "publish_fee": str(_publish_fee()),
            "pay_info": get_setting("pay_info") or PAY_INFO,
            "pay_zelle": get_setting("pay_zelle") or "",
            "pay_pago_movil": get_setting("pay_pago_movil") or "",
            "pay_usdt_trc20": get_setting("pay_usdt_trc20") or "",
            "pay_usdt_erc20": get_setting("pay_usdt_erc20") or "",
            "hide_demo": get_setting("hide_demo") or "0",
        },
    )


@app.get("/admin/kyc/{user_id}/{kind}")
def admin_kyc_photo(request: Request, user_id: int, kind: str):
    gate = _require_admin(request)
    if gate:
        return gate
    if kind not in ("id", "addr"):
        return RedirectResponse("/admin", status_code=302)
    user = get_user(user_id)
    if not user:
        return RedirectResponse("/admin", status_code=302)
    fname = user.get("kyc_id_photo") if kind == "id" else user.get("kyc_address_photo")
    if not fname:
        return RedirectResponse("/admin", status_code=302)
    path = os.path.join(KYC_DIR, os.path.basename(fname))
    if not os.path.isfile(path):
        return RedirectResponse("/admin", status_code=302)
    return FileResponse(path)


@app.post("/admin/kyc/{user_id}/aprobar")
def admin_kyc_approve(request: Request, user_id: int, note: str = Form("")):
    gate = _require_admin(request)
    if gate:
        return gate
    user = approve_kyc(user_id, note=note)
    if user and user.get("email") and not str(user.get("email") or "").endswith("@demo.motorcriollo"):
        _queue_mail(
            send_kyc_decision,
            user["email"],
            user.get("name") or "hola",
            approved=True,
            seller_code=user.get("seller_code") or "",
            note=note,
        )
    return RedirectResponse("/admin?tab=kyc", status_code=303)


@app.post("/admin/kyc/{user_id}/rechazar")
def admin_kyc_reject(request: Request, user_id: int, note: str = Form("")):
    gate = _require_admin(request)
    if gate:
        return gate
    user = reject_kyc(user_id, note=note or "Documentos no válidos")
    if user and user.get("email") and not str(user.get("email") or "").endswith("@demo.motorcriollo"):
        _queue_mail(
            send_kyc_decision,
            user["email"],
            user.get("name") or "hola",
            approved=False,
            note=note or "Documentos no válidos",
        )
    return RedirectResponse("/admin?tab=kyc", status_code=303)


@app.post("/admin/kyc/{user_id}/quitar")
def admin_kyc_revoke(request: Request, user_id: int, note: str = Form("")):
    gate = _require_admin(request)
    if gate:
        return gate
    revoke_kyc(user_id, note=note)
    return RedirectResponse("/admin?tab=users", status_code=303)


@app.post("/admin/ajustes")
def admin_settings_save(
    request: Request,
    commission: str = Form("80"),
    publish_fee: str = Form("50"),
    pay_info: str = Form(""),
    pay_zelle: str = Form(""),
    pay_pago_movil: str = Form(""),
    pay_usdt_trc20: str = Form(""),
    pay_usdt_erc20: str = Form(""),
    hide_demo: str = Form("0"),
):
    gate = _require_admin(request)
    if gate:
        return gate
    digits = "".join(c for c in commission if c.isdigit())
    set_setting("commission", digits or "80")
    pfee = "".join(c for c in publish_fee if c.isdigit())
    set_setting("publish_fee", pfee or "50")
    set_setting("pay_info", (pay_info or "").strip()[:800])
    set_setting("pay_zelle", (pay_zelle or "").strip()[:120])
    set_setting("pay_pago_movil", (pay_pago_movil or "").strip()[:120])
    set_setting("pay_usdt_trc20", (pay_usdt_trc20 or "").strip()[:120])
    set_setting("pay_usdt_erc20", (pay_usdt_erc20 or "").strip()[:120])
    if hide_demo not in ("1", "0"):
        hide_demo = "0"
    set_setting("hide_demo", hide_demo)
    return RedirectResponse("/admin?tab=ajustes", status_code=303)


@app.post("/admin/reporte/{report_id}/cerrar")
def admin_report_close(request: Request, report_id: int):
    gate = _require_admin(request)
    if gate:
        return gate
    close_report(report_id)
    return RedirectResponse("/admin?tab=reportes", status_code=303)


@app.post("/admin/deal/{deal_id}/pagado")
def admin_deal_paid(request: Request, deal_id: int):
    gate = _require_admin(request)
    if gate:
        return gate
    confirm_deal_paid(deal_id)
    return RedirectResponse("/admin?tab=pagos", status_code=303)


@app.post("/admin/listing/{listing_id}/publicado-pagado")
def admin_listing_publish_paid(request: Request, listing_id: int):
    gate = _require_admin(request)
    if gate:
        return gate
    listing = get_listing(listing_id)
    if listing and listing.get("status") == "pending_pay":
        update_listing(listing_id, status="active", publish_paid=1)
    return RedirectResponse("/admin?tab=listings", status_code=303)


@app.post("/admin/deal/{deal_id}/cancelar")
def admin_deal_cancel(request: Request, deal_id: int):
    gate = _require_admin(request)
    if gate:
        return gate
    cancel_deal(deal_id)
    return RedirectResponse("/admin?tab=pagos", status_code=303)


@app.post("/admin/listing/{listing_id}/inspeccion")
def admin_listing_inspect(request: Request, listing_id: int, inspected: int = Form(1)):
    gate = _require_admin(request)
    if gate:
        return gate
    update_listing(listing_id, inspected=1 if int(inspected or 0) else 0)
    return RedirectResponse("/admin?tab=listings", status_code=303)


@app.post("/admin/listing/{listing_id}/eliminar")
def admin_listing_delete(request: Request, listing_id: int):
    gate = _require_admin(request)
    if gate:
        return gate
    files = listing_file_paths(listing_id)
    delete_listing(listing_id)
    _remove_files(files)
    return RedirectResponse("/admin?tab=listings", status_code=303)


@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    return {"ok": True}


@app.get("/privado/{fname}")
def private_file(request: Request, fname: str):
    """Documentos del carro y comprobantes: solo el dueño del anuncio y administración."""
    m = _PRIVATE_NAME.match(fname or "")
    if not m:
        raise HTTPException(status_code=404)
    listing = get_listing(int(m.group(1)))
    user = me(request)
    owner = bool(listing and user and int(user["id"]) == int(listing["user_id"]))
    if not (owner or _admin(request)):
        raise HTTPException(status_code=404)
    path = os.path.join(PRIVATE_DIR, fname)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404)
    return FileResponse(path, headers={"Cache-Control": "private, no-store"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=PORT, reload=True)
