"""SQLite en local, Postgres en Render (DATABASE_URL)."""
from __future__ import annotations

import os
import sqlite3
from typing import Any

from config import DATABASE_URL, DB_PATH

USE_PG = bool(DATABASE_URL)


def backend_name() -> str:
    return "postgres" if USE_PG else "sqlite"


def _pg_url() -> str:
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


def connect():
    if USE_PG:
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(_pg_url(), row_factory=dict_row)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def sql(text: str) -> str:
    if not USE_PG:
        return text
    return text.replace("?", "%s")


def execute(con, text: str, params: tuple | list = ()):
    return con.execute(sql(text), params)


def insert_id(con, text: str, params: tuple | list = ()) -> int:
    if USE_PG:
        q = sql(text).rstrip().rstrip(";") + " RETURNING id"
        row = con.execute(q, params).fetchone()
        return int(row["id"] if isinstance(row, dict) else row[0])
    cur = con.execute(text, params)
    return int(cur.lastrowid)


def insert_ignore(con, text: str, params: tuple | list = ()) -> None:
    if USE_PG:
        q = text.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        if "ON CONFLICT" not in q.upper():
            q = q.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        con.execute(sql(q), params)
        return
    con.execute(text, params)


def integrity_error() -> tuple:
    errs = [sqlite3.IntegrityError]
    try:
        import psycopg

        errs.append(psycopg.IntegrityError)
    except ImportError:
        pass
    return tuple(errs)


def getv(row: Any, key: str, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default
