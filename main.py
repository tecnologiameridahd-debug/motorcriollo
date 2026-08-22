"""MotorCriollo — marketplace de carros usados (estilo Facebook Marketplace)."""
from __future__ import annotations

import os
import secrets
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    ADMIN_PASSWORD,
    BASE_DIR,
    MAX_PHOTOS,
    OAUTH_STATE_COOKIE,
    PERSISTENT,
    PORT,
    PUBLIC_BASE_URL,
    SESSION_COOKIE,
    SESSION_DAYS,
    UPLOAD_DIR,
    apple_enabled,
    google_enabled,
)
from email_utils import (
    email_ready,
    email_status,
    send_buyer_message,
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
    add_buyer_message,
    add_listing_photo,
    browse_listings,
    count_active_listings,
    create_listing,
    create_session,
    create_user,
    delete_listing,
    delete_session,
    delete_user,
    get_listing,
    get_user,
    get_user_by_email,
    init_db,
    list_user_listings,
    login,
    make_email_token,
    set_password,
    take_email_token,
    update_listing,
    update_profile,
    upsert_oauth_user,
    user_from_session,
)

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


def _page(request: Request, name: str, **ctx):
    ctx.setdefault("me", me(request))
    ctx.setdefault("_base", _base(request))
    ctx.setdefault("google_ok", google_enabled())
    ctx.setdefault("apple_ok", apple_enabled())
    ctx.setdefault("brands", BRANDS)
    ctx.setdefault("transmissions", TRANSMISSIONS)
    ctx.setdefault("fuel_types", FUEL_TYPES)
    ctx.setdefault("conditions", CONDITIONS)
    return templates.TemplateResponse(request, name, ctx)


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

@app.get("/", response_class=HTMLResponse)
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

    listings = browse_listings(
        q=q, brand=brand, price_min=_int(price_min), price_max=_int(price_max),
        year_min=_int(year_min), year_max=_int(year_max), city=city,
    )
    return _page(
        request, "index.html", listings=listings,
        filters={
            "q": q, "brand": brand, "price_min": price_min, "price_max": price_max,
            "year_min": year_min, "year_max": year_max, "city": city,
        },
        total=count_active_listings(),
    )


@app.get("/listing/{listing_id}", response_class=HTMLResponse)
def listing_detail(request: Request, listing_id: int):
    listing = get_listing(listing_id)
    if not listing:
        return RedirectResponse("/", status_code=302)
    seller = get_user(listing["user_id"])
    return _page(request, "listing.html", listing=listing, seller=seller)


@app.post("/listing/{listing_id}/contactar")
async def contactar_vendedor(
    request: Request,
    listing_id: int,
    buyer_name: str = Form(...),
    buyer_email: str = Form(""),
    buyer_phone: str = Form(""),
    message: str = Form(...),
):
    listing = get_listing(listing_id)
    if not listing:
        return RedirectResponse("/", status_code=302)
    seller = get_user(listing["user_id"])
    try:
        add_buyer_message(
            listing_id=listing_id,
            seller_id=listing["user_id"],
            buyer_name=buyer_name,
            buyer_email=buyer_email,
            buyer_phone=buyer_phone,
            message=message,
        )
    except ValueError as e:
        return _page(request, "listing.html", listing=listing, seller=seller, error=str(e))

    if seller and email_ready() and seller.get("email"):
        def _run():
            send_buyer_message(
                seller["email"], seller.get("name") or "vendedor", listing["title"],
                listing_id, buyer_name, buyer_email, buyer_phone, message,
            )

        threading.Thread(target=_run, name="mc-mail-buyer", daemon=True).start()

    return _page(request, "listing.html", listing=listing, seller=seller, sent=True)


# ----------------------------------------------------------- publicar ----

@app.get("/publicar", response_class=HTMLResponse)
def publicar_get(request: Request):
    user = me(request)
    if not user:
        return RedirectResponse("/login?next=/publicar", status_code=302)
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
):
    user = me(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    try:
        listing = create_listing(
            user_id=user["id"], title=title, brand=brand, model=model, year=year,
            price=price, mileage=mileage, transmission=transmission, fuel_type=fuel_type,
            condition=condition, description=description, city=city, state=state,
            phone=phone or user.get("phone") or "",
        )
        await _save_listing_photos(listing["id"], photos)
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


@app.get("/api/health")
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
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=PORT, reload=True)
