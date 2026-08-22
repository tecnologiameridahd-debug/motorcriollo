"""Login con Google (Gmail) y Sign in with Apple."""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from config import (
    APPLE_CLIENT_ID,
    APPLE_KEY_ID,
    APPLE_PRIVATE_KEY,
    APPLE_TEAM_ID,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    apple_enabled,
    google_enabled,
)


def _post(url: str, data: dict) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"OAuth error {e.code}: {detail[:300]}") from e


def _get_json(url: str, token: str) -> dict[str, Any]:
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def jwt_payload(token: str) -> dict[str, Any]:
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part.encode("ascii")))


def google_authorize_url(redirect_uri: str, state: str, hint: str = "") -> str:
    data = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    if hint == "gmail":
        data["login_hint"] = "@gmail.com"
    q = urllib.parse.urlencode(data)
    return f"https://accounts.google.com/o/oauth2/v2/auth?{q}"


def google_user(code: str, redirect_uri: str) -> dict[str, str]:
    tok = _post(
        "https://oauth2.googleapis.com/token",
        {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    info = _get_json(
        "https://www.googleapis.com/oauth2/v3/userinfo", tok["access_token"]
    )
    email = (info.get("email") or "").strip().lower()
    if not email:
        raise RuntimeError("Google no envió el email")
    return {
        "email": email,
        "name": (info.get("name") or email.split("@")[0])[:40],
        "photo": info.get("picture") or "",
        "oauth_id": info.get("sub") or email,
        "provider": "google",
    }


def apple_client_secret() -> str:
    import jwt

    now = int(time.time())
    return jwt.encode(
        {
            "iss": APPLE_TEAM_ID,
            "iat": now,
            "exp": now + 86400 * 120,
            "aud": "https://appleid.apple.com",
            "sub": APPLE_CLIENT_ID,
        },
        APPLE_PRIVATE_KEY,
        algorithm="ES256",
        headers={"kid": APPLE_KEY_ID, "alg": "ES256"},
    )


def apple_authorize_url(redirect_uri: str, state: str) -> str:
    q = urllib.parse.urlencode(
        {
            "client_id": APPLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "response_mode": "form_post",
            "scope": "name email",
            "state": state,
        }
    )
    return f"https://appleid.apple.com/auth/authorize?{q}"


def apple_user(code: str, redirect_uri: str, user_json: str = "") -> dict[str, str]:
    tok = _post(
        "https://appleid.apple.com/auth/token",
        {
            "code": code,
            "client_id": APPLE_CLIENT_ID,
            "client_secret": apple_client_secret(),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    claims = jwt_payload(tok["id_token"])
    email = (claims.get("email") or "").strip().lower()
    name = ""
    if user_json:
        try:
            extra = json.loads(user_json)
            n = extra.get("name") or {}
            name = f"{n.get('firstName', '')} {n.get('lastName', '')}".strip()
        except json.JSONDecodeError:
            name = ""
    if not email:
        email = f"apple_{claims.get('sub', 'user')}@privaterelay.appleid.com"
    return {
        "email": email,
        "name": (name or email.split("@")[0])[:40],
        "photo": "",
        "oauth_id": str(claims.get("sub") or email),
        "provider": "apple",
    }


__all__ = [
    "apple_authorize_url",
    "apple_enabled",
    "apple_user",
    "google_authorize_url",
    "google_enabled",
    "google_user",
]
