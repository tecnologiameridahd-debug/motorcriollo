"""SQLite storage for MotorCriollo (car classifieds)."""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from db import USE_PG, connect, execute, getv, insert_id, insert_ignore, integrity_error

TZ = timezone.utc

BRANDS = [
    "Toyota", "Honda", "Nissan", "Chevrolet", "Ford", "Hyundai", "Kia",
    "Volkswagen", "Mazda", "Jeep", "BMW", "Mercedes-Benz", "Audi", "Subaru",
    "Mitsubishi", "Suzuki", "Dodge", "Ram", "GMC", "Renault", "Otro",
]
TRANSMISSIONS = ["Automática", "Manual"]
FUEL_TYPES = ["Gasolina", "Diésel", "Híbrido", "Eléctrico", "GLP/GNV"]
CONDITIONS = ["Nuevo", "Usado - excelente", "Usado - bueno", "Usado - regular", "Para repuestos"]
STATUSES = ["active", "sold", "inactive"]


def _now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def init_db() -> None:
    con = connect()
    pk = "SERIAL PRIMARY KEY" if USE_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
    for stmt in (
        f"""CREATE TABLE IF NOT EXISTS users (
            id {pk}, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            name TEXT NOT NULL, phone TEXT DEFAULT '', city TEXT DEFAULT '',
            state TEXT DEFAULT '', is_demo INTEGER DEFAULT 0,
            created_at TEXT NOT NULL, last_seen TEXT NOT NULL,
            oauth_provider TEXT DEFAULT '', email_verified INTEGER DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL)""",
        f"""CREATE TABLE IF NOT EXISTS oauth_links (
            id {pk}, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider TEXT NOT NULL, oauth_id TEXT NOT NULL, UNIQUE(provider, oauth_id))""",
        """CREATE TABLE IF NOT EXISTS email_tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            expires_at INTEGER NOT NULL)""",
        f"""CREATE TABLE IF NOT EXISTS listings (
            id {pk},
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            brand TEXT NOT NULL,
            model TEXT NOT NULL,
            year INTEGER NOT NULL,
            price INTEGER NOT NULL,
            mileage INTEGER DEFAULT 0,
            transmission TEXT DEFAULT '',
            fuel_type TEXT DEFAULT '',
            condition TEXT DEFAULT '',
            description TEXT DEFAULT '',
            city TEXT DEFAULT '',
            state TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            is_demo INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)""",
        f"""CREATE TABLE IF NOT EXISTS listing_photos (
            id {pk},
            listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            position INTEGER DEFAULT 0)""",
        f"""CREATE TABLE IF NOT EXISTS buyer_messages (
            id {pk},
            listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
            seller_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            buyer_name TEXT NOT NULL,
            buyer_email TEXT DEFAULT '',
            buyer_phone TEXT DEFAULT '',
            message TEXT NOT NULL,
            created_at TEXT NOT NULL)""",
    ):
        con.execute(stmt)
    if not USE_PG:
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status, created_at)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_listings_user ON listings(user_id)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_photos_listing ON listing_photos(listing_id, position)"
        )
    else:
        for stmt in (
            "CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_listings_user ON listings(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_photos_listing ON listing_photos(listing_id, position)",
        ):
            try:
                con.execute(stmt)
            except Exception:
                pass
    con.commit()
    con.close()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 180_000)
    return salt.hex() + ":" + dk.hex()


def check_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 180_000)
        return secrets.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    if not r:
        return None
    d = dict(r)
    d.pop("password_hash", None)
    return d


# ---------------------------------------------------------------- users ----

def create_user(
    *,
    email: str,
    password: str,
    name: str,
    phone: str = "",
    city: str = "",
    state: str = "",
    is_demo: bool = False,
) -> dict[str, Any]:
    email = email.strip().lower()
    name = (name or "").strip()[:60]
    if "@" not in email or len(password) < 4:
        raise ValueError("Email o contraseña inválidos")
    if not name:
        raise ValueError("Pon tu nombre")
    con = connect()
    try:
        uid = insert_id(
            con,
            """
            INSERT INTO users(email, password_hash, name, phone, city, state,
                              is_demo, created_at, last_seen, email_verified)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                email,
                hash_password(password),
                name,
                (phone or "")[:30],
                (city or "")[:60],
                (state or "")[:60],
                1 if is_demo else 0,
                _now(),
                _now(),
                1 if is_demo else 0,
            ),
        )
        con.commit()
    except integrity_error():
        con.close()
        raise ValueError("Ese email ya está registrado")
    con.close()
    return get_user(uid)


def get_user(user_id: int) -> dict[str, Any] | None:
    con = connect()
    r = execute(con, "SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    con.close()
    return _row(r)


def get_user_by_email(email: str) -> Any:
    con = connect()
    r = execute(
        con, "SELECT * FROM users WHERE email=?", (email.strip().lower(),)
    ).fetchone()
    con.close()
    return r


def upsert_oauth_user(
    *, email: str, name: str, provider: str, oauth_id: str
) -> tuple[dict[str, Any], bool]:
    email = (email or "").strip().lower()
    name = (name or email.split("@")[0] or "Usuario")[:60]
    con = connect()
    link = execute(
        con,
        "SELECT user_id FROM oauth_links WHERE provider=? AND oauth_id=?",
        (provider, oauth_id),
    ).fetchone()
    if link:
        uid = getv(link, "user_id")
        execute(con, "UPDATE users SET last_seen=? WHERE id=?", (_now(), uid))
        con.commit()
        con.close()
        return get_user(uid), False

    row = execute(con, "SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if row:
        uid = getv(row, "id")
        insert_ignore(
            con,
            "INSERT OR IGNORE INTO oauth_links(user_id, provider, oauth_id) VALUES(?,?,?)",
            (uid, provider, oauth_id),
        )
        execute(
            con,
            "UPDATE users SET oauth_provider=?, last_seen=? WHERE id=?",
            (provider, _now(), uid),
        )
        con.commit()
        con.close()
        return get_user(uid), False

    uid = insert_id(
        con,
        """
        INSERT INTO users(email, password_hash, name, phone, city, state,
                          is_demo, created_at, last_seen, oauth_provider, email_verified)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            email,
            hash_password(secrets.token_urlsafe(24)),
            name,
            "",
            "",
            "",
            0,
            _now(),
            _now(),
            provider,
            1,
        ),
    )
    execute(
        con,
        "INSERT INTO oauth_links(user_id, provider, oauth_id) VALUES(?,?,?)",
        (uid, provider, oauth_id),
    )
    con.commit()
    con.close()
    return get_user(uid), True


def login(email: str, password: str) -> dict[str, Any] | None:
    row = get_user_by_email(email)
    if not row or not check_password(password, row["password_hash"]):
        return None
    touch(row["id"])
    return get_user(row["id"])


def touch(user_id: int) -> None:
    con = connect()
    execute(con, "UPDATE users SET last_seen=? WHERE id=?", (_now(), user_id))
    con.commit()
    con.close()


def update_profile(user_id: int, **fields) -> dict[str, Any] | None:
    allowed = {"name", "phone", "city", "state", "email_verified"}
    sets, vals = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "name":
            v = (v or "").strip()[:60]
        if k in ("phone",):
            v = (v or "").strip()[:30]
        if k in ("city", "state"):
            v = (v or "").strip()[:60]
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        return get_user(user_id)
    vals.append(user_id)
    con = connect()
    execute(con, f"UPDATE users SET {', '.join(sets)} WHERE id=?", vals)
    con.commit()
    con.close()
    return get_user(user_id)


def set_password(user_id: int, password: str) -> None:
    if len(password or "") < 4:
        raise ValueError("Contraseña muy corta")
    con = connect()
    execute(
        con,
        "UPDATE users SET password_hash=? WHERE id=?",
        (hash_password(password), int(user_id)),
    )
    con.commit()
    con.close()


def delete_user(user_id: int) -> None:
    con = connect()
    execute(con, "DELETE FROM sessions WHERE user_id=?", (user_id,))
    execute(con, "DELETE FROM users WHERE id=?", (user_id,))
    con.commit()
    con.close()


# -------------------------------------------------------------- sessions ----

def create_session(user_id: int, days: int = 30) -> str:
    token = secrets.token_urlsafe(32)
    exp = int(time.time()) + days * 86400
    con = connect()
    execute(
        con,
        "INSERT INTO sessions(token, user_id, expires_at) VALUES(?,?,?)",
        (token, user_id, exp),
    )
    con.commit()
    con.close()
    return token


def user_from_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    con = connect()
    r = execute(
        con,
        "SELECT user_id FROM sessions WHERE token=? AND expires_at>?",
        (token, int(time.time())),
    ).fetchone()
    con.close()
    if not r:
        return None
    uid = getv(r, "user_id")
    touch(uid)
    return get_user(uid)


def delete_session(token: str | None) -> None:
    if not token:
        return
    con = connect()
    execute(con, "DELETE FROM sessions WHERE token=?", (token,))
    con.commit()
    con.close()


# -------------------------------------------------------------- email tok ----

def make_email_token(user_id: int, kind: str, hours: int = 24) -> str:
    token = secrets.token_urlsafe(24)
    con = connect()
    execute(con, "DELETE FROM email_tokens WHERE user_id=? AND kind=?", (int(user_id), kind))
    execute(
        con,
        "INSERT INTO email_tokens(token, user_id, kind, expires_at) VALUES(?,?,?,?)",
        (token, int(user_id), kind, int(time.time()) + hours * 3600),
    )
    con.commit()
    con.close()
    return token


def take_email_token(token: str, kind: str) -> int | None:
    con = connect()
    row = execute(
        con,
        "SELECT user_id, expires_at FROM email_tokens WHERE token=? AND kind=?",
        ((token or "").strip(), kind),
    ).fetchone()
    if not row:
        con.close()
        return None
    if int(getv(row, "expires_at") or 0) < int(time.time()):
        execute(con, "DELETE FROM email_tokens WHERE token=?", ((token or "").strip(),))
        con.commit()
        con.close()
        return None
    uid = int(getv(row, "user_id"))
    execute(con, "DELETE FROM email_tokens WHERE token=?", ((token or "").strip(),))
    con.commit()
    con.close()
    return uid


# --------------------------------------------------------------- listings ----

def _listing_row(r: Any) -> dict[str, Any] | None:
    if not r:
        return None
    d = dict(r)
    photos = list_listing_photos(d["id"])
    d["photos"] = photos
    d["photo"] = photos[0] if photos else ""
    return d


def create_listing(
    *,
    user_id: int,
    title: str,
    brand: str,
    model: str,
    year: int,
    price: int,
    mileage: int = 0,
    transmission: str = "",
    fuel_type: str = "",
    condition: str = "",
    description: str = "",
    city: str = "",
    state: str = "",
    phone: str = "",
    is_demo: bool = False,
) -> dict[str, Any]:
    title = (title or "").strip()[:120]
    if not title:
        raise ValueError("Ponle un título al anuncio")
    if not brand or not model:
        raise ValueError("Marca y modelo son obligatorios")
    try:
        year = int(year)
        price = int(price)
        mileage = int(mileage or 0)
    except (TypeError, ValueError):
        raise ValueError("Año, precio y kilometraje deben ser números")
    if year < 1950 or year > datetime.now(TZ).year + 1:
        raise ValueError("Año inválido")
    if price < 0:
        raise ValueError("Precio inválido")
    con = connect()
    lid = insert_id(
        con,
        """
        INSERT INTO listings(user_id, title, brand, model, year, price, mileage,
                             transmission, fuel_type, condition, description,
                             city, state, phone, status, is_demo, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id, title, brand[:40], model[:60], year, price, mileage,
            transmission[:20], fuel_type[:20], condition[:30], (description or "")[:2000],
            (city or "")[:60], (state or "")[:60], (phone or "")[:30], "active",
            1 if is_demo else 0, _now(), _now(),
        ),
    )
    con.commit()
    con.close()
    return get_listing(lid)


def update_listing(listing_id: int, **fields) -> dict[str, Any] | None:
    allowed = {
        "title", "brand", "model", "year", "price", "mileage", "transmission",
        "fuel_type", "condition", "description", "city", "state", "phone", "status",
    }
    sets, vals = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "title":
            v = (v or "").strip()[:120]
        if k in ("brand",):
            v = (v or "")[:40]
        if k in ("model",):
            v = (v or "")[:60]
        if k in ("transmission", "fuel_type"):
            v = (v or "")[:20]
        if k == "condition":
            v = (v or "")[:30]
        if k == "description":
            v = (v or "")[:2000]
        if k in ("city", "state"):
            v = (v or "")[:60]
        if k == "phone":
            v = (v or "")[:30]
        if k in ("year", "price", "mileage"):
            v = int(v or 0)
        if k == "status" and v not in STATUSES:
            continue
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        return get_listing(listing_id)
    sets.append("updated_at=?")
    vals.append(_now())
    vals.append(listing_id)
    con = connect()
    execute(con, f"UPDATE listings SET {', '.join(sets)} WHERE id=?", vals)
    con.commit()
    con.close()
    return get_listing(listing_id)


def get_listing(listing_id: int) -> dict[str, Any] | None:
    con = connect()
    r = execute(con, "SELECT * FROM listings WHERE id=?", (listing_id,)).fetchone()
    con.close()
    return _listing_row(r)


def delete_listing(listing_id: int) -> None:
    con = connect()
    execute(con, "DELETE FROM listing_photos WHERE listing_id=?", (listing_id,))
    execute(con, "DELETE FROM listings WHERE id=?", (listing_id,))
    con.commit()
    con.close()


def list_user_listings(user_id: int) -> list[dict[str, Any]]:
    con = connect()
    rows = execute(
        con,
        "SELECT * FROM listings WHERE user_id=? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    con.close()
    return [_listing_row(r) for r in rows]


def browse_listings(
    *,
    q: str = "",
    brand: str = "",
    price_min: int | None = None,
    price_max: int | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    city: str = "",
    limit: int = 60,
) -> list[dict[str, Any]]:
    where = ["status='active'"]
    params: list[Any] = []
    if q:
        like = f"%{q.strip().lower()}%"
        where.append(
            "(LOWER(title) LIKE ? OR LOWER(brand) LIKE ? OR LOWER(model) LIKE ? OR LOWER(description) LIKE ?)"
        )
        params += [like, like, like, like]
    if brand:
        where.append("brand=?")
        params.append(brand)
    if price_min is not None:
        where.append("price>=?")
        params.append(price_min)
    if price_max is not None:
        where.append("price<=?")
        params.append(price_max)
    if year_min is not None:
        where.append("year>=?")
        params.append(year_min)
    if year_max is not None:
        where.append("year<=?")
        params.append(year_max)
    if city:
        where.append("LOWER(city) LIKE ?")
        params.append(f"%{city.strip().lower()}%")
    sql_text = (
        "SELECT * FROM listings WHERE " + " AND ".join(where)
        + " ORDER BY created_at DESC LIMIT ?"
    )
    params.append(limit)
    con = connect()
    rows = execute(con, sql_text, params).fetchall()
    con.close()
    return [_listing_row(r) for r in rows]


def count_active_listings() -> int:
    con = connect()
    r = execute(con, "SELECT COUNT(*) AS n FROM listings WHERE status='active'").fetchone()
    con.close()
    return int(getv(r, "n") or 0)


# ---------------------------------------------------------------- photos ----

def add_listing_photo(listing_id: int, path: str, position: int = 0) -> None:
    con = connect()
    insert_id(
        con,
        "INSERT INTO listing_photos(listing_id, path, position) VALUES(?,?,?)",
        (listing_id, path, position),
    )
    con.commit()
    con.close()


def list_listing_photos(listing_id: int) -> list[str]:
    con = connect()
    rows = execute(
        con,
        "SELECT path FROM listing_photos WHERE listing_id=? ORDER BY position ASC, id ASC",
        (listing_id,),
    ).fetchall()
    con.close()
    return [getv(r, "path") for r in rows]


def delete_listing_photos(listing_id: int) -> None:
    con = connect()
    execute(con, "DELETE FROM listing_photos WHERE listing_id=?", (listing_id,))
    con.commit()
    con.close()


# ------------------------------------------------------------- messages ----

def add_buyer_message(
    *,
    listing_id: int,
    seller_id: int,
    buyer_name: str,
    buyer_email: str = "",
    buyer_phone: str = "",
    message: str,
) -> dict[str, Any]:
    buyer_name = (buyer_name or "").strip()[:60]
    message = (message or "").strip()[:1000]
    if not buyer_name or not message:
        raise ValueError("Nombre y mensaje son obligatorios")
    con = connect()
    mid = insert_id(
        con,
        """
        INSERT INTO buyer_messages(listing_id, seller_id, buyer_name, buyer_email,
                                   buyer_phone, message, created_at)
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            listing_id, seller_id, buyer_name, (buyer_email or "").strip()[:120],
            (buyer_phone or "").strip()[:30], message, _now(),
        ),
    )
    con.commit()
    con.close()
    return {
        "id": mid,
        "listing_id": listing_id,
        "seller_id": seller_id,
        "buyer_name": buyer_name,
        "buyer_email": buyer_email,
        "buyer_phone": buyer_phone,
        "message": message,
    }


def list_seller_messages(seller_id: int, limit: int = 50) -> list[dict[str, Any]]:
    con = connect()
    rows = execute(
        con,
        "SELECT * FROM buyer_messages WHERE seller_id=? ORDER BY created_at DESC LIMIT ?",
        (seller_id, limit),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def count_users() -> int:
    con = connect()
    r = execute(con, "SELECT COUNT(*) AS n FROM users").fetchone()
    con.close()
    return int(getv(r, "n") or 0)
