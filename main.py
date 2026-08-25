"""MotorCriollo — marketplace de carros usados (estilo Facebook Marketplace)."""
from __future__ import annotations

import os
import secrets
import threading
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    BASE_DIR,
    COMMISSION_USD,
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
from storage import (
    BRANDS,
    CONDITIONS,
    FUEL_TYPES,
    TRANSMISSIONS,
    accept_deal,
    add_chat_message,
    add_listing_photo,
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
    init_db,
    list_all_listings,
    list_chat_messages,
    list_conversations,
    list_deals,
    list_kyc,
    list_reports,
    list_user_listings,
    list_users_admin,
    login,
    make_email_token,
    reject_kyc,
    revoke_kyc,
    set_deal_proof,
    set_setting,
    set_password,
    submit_kyc,
    take_email_token,
    update_listing,
    update_profile,
    upsert_oauth_user,
    user_from_session,
)

ADMIN_COOKIE = "mc_admin"

app = FastAPI(title="MotorCriollo")
app.mount("/static/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.on_event("startup")
def _startup():
    init_db()
    seed()


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
    ctx.setdefault("google_ok", google_enabled())
    ctx.setdefault("apple_ok", apple_enabled())
    ctx.setdefault("brands", BRANDS)
    ctx.setdefault("transmissions", TRANSMISSIONS)
    ctx.setdefault("fuel_types", FUEL_TYPES)
    ctx.setdefault("conditions", CONDITIONS)
    ctx.setdefault("commission", _commission())
    ctx.setdefault("pay_info", _pay_info())
    return templates.TemplateResponse(request, name, ctx)


def _commission() -> int:
    raw = (get_setting("commission") or "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return int(COMMISSION_USD)


def _pay_info() -> str:
    return (get_setting("pay_info") or "").strip() or PAY_INFO


def _queue_mail(fn, *args, **kwargs) -> None:
    if not email_ready():
        return

    def _run():
        try:
            fn(*args, **kwargs)
        except Exception as e:
            print(f"[mail] {type(e).__name__}: {e}")

    threading.Thread(target=_run, name="mc-mail", daemon=True).start()


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


async def _save_photo(listing_id: int, photo: UploadFile | None) -> str:
    if not photo or not photo.filename:
        return ""
    ext = Path(photo.filename).suffix.lower()
    check = _PHOTO_MAGIC.get(ext)
    if not check:
        raise ValueError("Foto: usa jpg, png, gif o webp")
    data = await photo.read()
    if len(data) < 80:
        return ""
    if not check(data):
        raise ValueError("El archivo no es una imagen válida")
    fname = f"{listing_id}_{secrets.token_hex(6)}{ext}"
    dest = os.path.join(UPLOAD_DIR, fname)
    with open(dest, "wb") as f:
        f.write(data)
    return f"/static/uploads/{fname}"


async def _save_kyc_photo(user_id: int, kind: str, photo: UploadFile | None) -> str:
    if not photo or not photo.filename:
        return ""
    ext = Path(photo.filename).suffix.lower()
    check = _PHOTO_MAGIC.get(ext)
    if not check:
        raise ValueError("Foto: usa jpg, png, gif o webp")
    data = await photo.read()
    if len(data) < 80:
        raise ValueError("La foto está vacía o dañada")
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("La foto pesa más de 8 MB")
    if not check(data):
        raise ValueError("El archivo no es una imagen válida")
    fname = f"{int(user_id)}_{kind}{ext}"
    dest = os.path.join(KYC_DIR, fname)
    with open(dest, "wb") as f:
        f.write(data)
    return fname


async def _save_listing_photos(listing_id: int, files: list[UploadFile | None]) -> int:
    n = 0
    for i, up in enumerate(files):
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
    resp = RedirectResponse("/", status_code=303)
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
):
    def _int(v: str):
        v = (v or "").strip()
        return int(v) if v.isdigit() else None

    show_demo = not hide_demo_now()
    listings = browse_listings(
        q=q, brand=brand, price_min=_int(price_min), price_max=_int(price_max),
        year_min=_int(year_min), year_max=_int(year_max), city=city,
        include_demo=show_demo,
    )
    return _page(
        request, "index.html", listings=listings,
        filters={
            "q": q, "brand": brand, "price_min": price_min, "price_max": price_max,
            "year_min": year_min, "year_max": year_max, "city": city,
        },
        total=count_active_listings(include_demo=show_demo),
    )


@app.get("/listing/{listing_id}", response_class=HTMLResponse)
def _share(request: Request, listing: dict) -> dict:
    url = f"{_base(request)}/listing/{listing['id']}"
    price = "{:,}".format(int(listing.get("price") or 0)).replace(",", ".")
    text = f"{listing.get('title') or 'Carro'} ${price} en MotorCriollo"
    full = f"{text} {url}"
    photo = listing.get("photo") or ""
    if photo.startswith("/"):
        photo = _base(request) + photo
    return {
        "url": url,
        "text": text,
        "image": photo,
        "wa": "https://wa.me/?text=" + quote(full),
        "fb": "https://www.facebook.com/sharer/sharer.php?u=" + quote(url),
        "x": "https://twitter.com/intent/tweet?text=" + quote(text) + "&url=" + quote(url),
        "sms": "sms:?&body=" + quote(full),
    }


def listing_detail(request: Request, listing_id: int):
    listing = get_listing(listing_id)
    if not listing:
        return RedirectResponse("/", status_code=302)
    seller = get_user(listing["user_id"])
    return _page(
        request, "listing.html", listing=listing, seller=seller, reported=False,
        share=_share(request, listing),
    )


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
    )


@app.get("/chat/{listing_id}")
def chat_start(request: Request, listing_id: int):
    user = me(request)
    if not user:
        return RedirectResponse(f"/login?next=/chat/{listing_id}", status_code=302)
    listing = get_listing(listing_id)
    if not listing:
        return RedirectResponse("/", status_code=302)
    if int(user["id"]) == int(listing["user_id"]):
        return RedirectResponse("/mensajes", status_code=302)
    try:
        convo = get_or_create_conversation(listing_id, user["id"], listing["user_id"])
    except ValueError as e:
        return _page(request, "listing.html", listing=listing, seller=get_user(listing["user_id"]), error=str(e))
    return RedirectResponse(f"/c/{convo['id']}", status_code=302)


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
    return _page(
        request,
        "chat.html",
        convo=convo,
        listing=listing,
        other=get_user(other_id),
        messages=list_chat_messages(cid),
        deal=get_deal_by_conversation(cid),
        i_am_seller=int(user["id"]) == int(convo["seller_id"]),
        error=error,
    )


@app.post("/c/{cid}/mensaje")
def chat_send(request: Request, cid: int, body: str = Form(...)):
    user = me(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    try:
        add_chat_message(cid, user["id"], body)
    except ValueError:
        return RedirectResponse(f"/c/{cid}", status_code=303)
    convo = get_conversation(cid)
    if convo:
        other_id = convo["seller_id"] if int(user["id"]) == int(convo["buyer_id"]) else convo["buyer_id"]
        other = get_user(other_id)
        listing = get_listing(convo["listing_id"])
        if other and other.get("email") and not str(other.get("email") or "").endswith("@demo.motorcriollo"):
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
    path = await _save_photo(deal["listing_id"], proof)
    if not path:
        return chat_view(request, cid, error="Sube una foto o captura del pago")
    set_deal_proof(deal["id"], path)
    add_chat_message(cid, user["id"], "Subí el comprobante de la comisión. Administración lo revisa.")
    return RedirectResponse(f"/c/{cid}", status_code=303)


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
        ser = await _save_photo(listing["id"], photo_serial)
        tit = await _save_photo(listing["id"], photo_title)
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
        ser = await _save_photo(listing_id, photo_serial)
        tit = await _save_photo(listing_id, photo_title)
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
    if status in ("active", "sold", "inactive"):
        update_listing(listing_id, status=status)
    return RedirectResponse("/mis-publicaciones", status_code=303)


@app.post("/listing/{listing_id}/eliminar")
def eliminar_listing(request: Request, listing_id: int):
    user = me(request)
    listing = get_listing(listing_id)
    if not listing or not user or user["id"] != listing["user_id"]:
        return RedirectResponse("/login", status_code=302)
    delete_listing(listing_id)
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
def registro_get(request: Request):
    if me(request):
        return RedirectResponse("/", status_code=302)
    return _page(request, "registro.html")


@app.post("/registro")
def registro_post(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    phone: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
):
    try:
        user = create_user(
            email=email, password=password, name=name, phone=phone, city=city, state=state,
        )
        _queue_verify_email(user)
        _queue_welcome_email(user)
    except ValueError as e:
        return _page(request, "registro.html", error=str(e))
    token = create_session(user["id"], SESSION_DAYS)
    resp = RedirectResponse("/", status_code=303)
    return _set_session(resp, token)


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request, next: str = ""):
    if me(request):
        return RedirectResponse("/", status_code=302)
    return _page(request, "login.html", next=next)


@app.post("/login")
def login_post(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("")):
    user = login(email, password)
    if not user:
        return _page(request, "login.html", error="Email o contraseña incorrectos", next=next)
    token = create_session(user["id"], SESSION_DAYS)
    resp = RedirectResponse(next or "/", status_code=303)
    return _set_session(resp, token)


@app.get("/terminos", response_class=HTMLResponse)
def terminos(request: Request):
    return _page(request, "terminos.html")


@app.get("/privacidad", response_class=HTMLResponse)
def privacidad(request: Request):
    return _page(request, "privacidad.html")


@app.get("/salir")
def salir(request: Request):
    delete_session(request.cookies.get(SESSION_COOKIE))
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get("/auth/google")
def auth_google(request: Request):
    if not google_enabled():
        return _page(
            request, "login.html",
            error="Falta el ID de Google. En Render → MotorCriollo → Environment pega "
                  "MOTORCRIOLLO_GOOGLE_CLIENT_ID y MOTORCRIOLLO_GOOGLE_CLIENT_SECRET.",
        )
    state = secrets.token_urlsafe(24)
    url = google_authorize_url(f"{_base(request)}/auth/google/callback", state)
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax")
    return resp


@app.get("/auth/google/callback")
def auth_google_cb(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return _page(request, "login.html", error=f"Google: {error}")
    saved = request.cookies.get(OAUTH_STATE_COOKIE)
    if not code or not saved or saved != state:
        return _page(request, "login.html", error="Sesión de Google inválida. Intenta de nuevo.")
    try:
        info = google_user(code, f"{_base(request)}/auth/google/callback")
        user, is_new = upsert_oauth_user(
            email=info["email"], name=info["name"], provider="google", oauth_id=info["oauth_id"],
        )
    except Exception as e:
        return _page(request, "login.html", error=f"Google no conectó: {e}")
    return _finish_oauth(request, user, is_new)


@app.get("/auth/apple")
def auth_apple(request: Request):
    if not apple_enabled():
        return _page(
            request, "login.html",
            error="Falta configurar Apple. Pega APPLE_CLIENT_ID, TEAM, KEY y el archivo .p8 en config_local.py",
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
        return _page(request, "login.html", error=f"Apple: {err}")
    saved = request.cookies.get(OAUTH_STATE_COOKIE)
    if not code or not saved or saved != state:
        return _page(request, "login.html", error="Sesión de Apple inválida. Intenta de nuevo.")
    try:
        info = apple_user(code, f"{_base(request)}/auth/apple/callback", user_json)
        user, is_new = upsert_oauth_user(
            email=info["email"], name=info["name"], provider="apple", oauth_id=info["oauth_id"],
        )
    except Exception as e:
        return _page(request, "login.html", error=f"Apple no conectó: {e}")
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
    _queue_verify_email(user)
    return RedirectResponse("/mis-publicaciones", status_code=303)


@app.get("/olvide", response_class=HTMLResponse)
def olvide_get(request: Request):
    return _page(request, "olvide.html")


@app.post("/olvide")
def olvide_post(request: Request, email: str = Form(...)):
    row = get_user_by_email(email)
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
    uid = take_email_token(token, "reset")
    if not uid:
        return _page(request, "olvide.html", error="El enlace no vale o ya se usó.")
    try:
        set_password(uid, password)
    except ValueError as e:
        return _page(request, "reset.html", token=token, error=str(e))
    return _page(request, "login.html", info="ok")


@app.post("/eliminar-cuenta")
def eliminar_cuenta(request: Request):
    user = me(request)
    if not user:
        return RedirectResponse("/", status_code=302)
    delete_user(user["id"])
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


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
    want = admin_password()
    if not want or password != want:
        return _page(request, "admin_login.html", error="Clave incorrecta")
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


@app.get("/admin/salir")
def admin_logout(request: Request):
    delete_admin_session(request.cookies.get(ADMIN_COOKIE))
    resp = RedirectResponse("/admin/entrar", status_code=302)
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
            "pay_info": _pay_info(),
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
    commission: str = Form("20"),
    pay_info: str = Form(""),
    hide_demo: str = Form("auto"),
):
    gate = _require_admin(request)
    if gate:
        return gate
    digits = "".join(c for c in commission if c.isdigit())
    set_setting("commission", digits or "20")
    set_setting("pay_info", (pay_info or "").strip()[:800])
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
    delete_listing(listing_id)
    return RedirectResponse("/admin?tab=listings", status_code=303)


@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    from db import backend_name

    return {
        "ok": True,
        "app": "MotorCriollo",
        "backend": backend_name(),
        "persistent": PERSISTENT,
        "google": google_enabled(),
        "email": email_status(),
        "listings": count_active_listings(),
        "users": count_users(),
        "kyc_pending": count_kyc_pending(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=PORT, reload=True)
