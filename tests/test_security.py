import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

import main
import storage
import stripe_pay
from seed import seed

client = TestClient(main.app)
client.__enter__()  # dispara startup (init_db + seed)

PWD = "clave-segura-123"


def _user(email, verified=True, kyc=True):
    u = storage.create_user(email=email, password=PWD, name="Prueba")
    if verified:
        storage.update_profile(u["id"], email_verified=1)
    if kyc:
        storage.approve_kyc(u["id"])
    return storage.get_user(u["id"])


def _login_client(user):
    c = TestClient(main.app)
    c.cookies.set(main.SESSION_COOKIE, storage.create_session(user["id"]))
    return c


def _pending_listing(user, sid="cs_test_pub_1", cents=5000):
    l = storage.create_listing(
        user_id=user["id"], title="Corolla 2019", brand="Toyota", model="Corolla",
        year=2019, price=9000, city="Caracas", state="Distrito Capital", phone="+58 412",
    )
    storage.update_listing(l["id"], stripe_publish_session=sid, publish_cents=cents)
    return storage.get_listing(l["id"])


def _sess(sid, kind, target, cents, app="motorcriollo", paid=True, currency="usd"):
    key = "listing_id" if kind == "publish" else "deal_id"
    return {
        "id": sid, "payment_status": "paid" if paid else "unpaid", "status": "complete",
        "mode": "payment", "currency": currency, "amount_total": cents,
        "metadata": {"app": app, "kind": kind, key: str(target), "amount_cents": str(cents)},
    }


# ------------------------------------------------------------ producción ----

def test_docs_disabled_and_health_minimal():
    for p in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(p).status_code == 404
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_security_headers_present():
    r = client.get("/")
    assert r.status_code == 200
    h = r.headers
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["x-frame-options"] == "DENY"
    assert h["x-content-type-options"] == "nosniff"
    assert "strict-origin" in h["referrer-policy"]
    assert "max-age=" in h["strict-transport-security"]


def test_cross_origin_post_blocked():
    r = client.post("/login", data={"email": "a@b.c", "password": "x"},
                    headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_main_pages_render():
    for p in ("/", "/blog", "/login", "/registro", "/olvide", "/terminos", "/privacidad",
              "/estados/zulia", "/carros/caracas", "/robots.txt", "/sitemap.xml", "/admin/entrar"):
        assert client.get(p).status_code == 200, p


# ----------------------------------------------------------------- demo ----

def test_demo_accounts_locked_and_hidden():
    # cuenta demo "vieja" con clave conocida, verificada y con sesión activa
    u = storage.create_user(email="viejo@demo.motorcriollo", password="demo1234",
                            name="Demo", is_demo=True)
    storage.approve_kyc(u["id"])
    tok = storage.create_session(u["id"])
    storage.create_listing(user_id=u["id"], title="Demo Aveo", brand="Chevrolet",
                           model="Aveo", year=2014, price=3000, phone="1", is_demo=True)
    seed()  # en producción: bloquea, no siembra
    assert storage.login("viejo@demo.motorcriollo", "demo1234") is None
    assert storage.user_from_session(tok) is None
    assert storage.get_user(u["id"])["kyc_status"] == "none"
    assert not storage.can_publish(storage.get_user(u["id"]))
    assert "Demo Aveo" not in client.get("/").text
    assert "/carro/" not in client.get("/sitemap.xml").text.replace("/carros/", "")
    demo = [l for l in storage.list_user_listings(u["id"])][0]
    assert client.get(f"/carro/{main.listing_slug(demo)}").status_code == 404


# ----------------------------------------------------------------- stripe ----

def test_verify_paid_session_rules():
    ok, _ = stripe_pay.verify_paid_session(
        _sess("cs1", "publish", 7, 5000), kind="publish", target_id=7,
        expected_cents=5000, stored_session_id="cs1")
    assert ok
    bad = [
        (_sess("cs1", "commission", 7, 5000), "cs1", 5000),   # otro tipo
        (_sess("cs1", "publish", 8, 5000), "cs1", 5000),      # otro anuncio
        (_sess("cs1", "publish", 7, 100), "cs1", 5000),       # monto
        (_sess("cs1", "publish", 7, 5000, currency="eur"), "cs1", 5000),
        (_sess("cs1", "publish", 7, 5000, app="dateradar"), "cs1", 5000),
        (_sess("cs1", "publish", 7, 5000, paid=False), "cs1", 5000),
        (_sess("cs1", "publish", 7, 5000), "cs_otro", 5000),  # no es la guardada
    ]
    for sess, stored, cents in bad:
        ok, _ = stripe_pay.verify_paid_session(
            sess, kind="publish", target_id=7, expected_cents=cents, stored_session_id=stored)
        assert not ok, sess


def test_claim_session_only_once():
    assert storage.claim_stripe_session("cs_once", "publish", 1) == (True, True)
    assert storage.claim_stripe_session("cs_once", "publish", 1) == (True, False)
    assert storage.claim_stripe_session("cs_once", "publish", 2)[0] is False
    assert storage.claim_stripe_session("cs_once", "commission", 1)[0] is False


def test_publish_return_rejects_commission_session(monkeypatch):
    u = _user("vend1@x.com")
    l = _pending_listing(u, sid="cs_mix")
    monkeypatch.setattr(stripe_pay, "retrieve_session",
                        lambda sid: _sess(sid, "commission", 99, 8000))
    c = _login_client(u)
    c.get(f"/listing/{l['id']}/publicado-ok?session_id=cs_mix", follow_redirects=False)
    assert storage.get_listing(l["id"])["status"] == "pending_pay"


def test_publish_return_wrong_amount_and_ok(monkeypatch):
    u = _user("vend2@x.com")
    l = _pending_listing(u, sid="cs_amt", cents=5000)
    c = _login_client(u)
    monkeypatch.setattr(stripe_pay, "retrieve_session",
                        lambda sid: _sess(sid, "publish", l["id"], 100))
    c.get(f"/listing/{l['id']}/publicado-ok?session_id=cs_amt", follow_redirects=False)
    assert storage.get_listing(l["id"])["status"] == "pending_pay"
    monkeypatch.setattr(stripe_pay, "retrieve_session",
                        lambda sid: _sess(sid, "publish", l["id"], 5000))
    c.get(f"/listing/{l['id']}/publicado-ok?session_id=cs_amt", follow_redirects=False)
    assert storage.get_listing(l["id"])["status"] == "active"


def test_paid_session_cannot_activate_second_listing(monkeypatch):
    u = _user("vend3@x.com")
    a = _pending_listing(u, sid="cs_reuse")
    b = _pending_listing(u, sid="cs_b")
    monkeypatch.setattr(stripe_pay, "retrieve_session",
                        lambda sid: _sess("cs_reuse", "publish", a["id"], 5000))
    c = _login_client(u)
    c.get(f"/listing/{a['id']}/publicado-ok?session_id=cs_reuse", follow_redirects=False)
    c.get(f"/listing/{b['id']}/publicado-ok?session_id=cs_reuse", follow_redirects=False)
    assert storage.get_listing(a["id"])["status"] == "active"
    assert storage.get_listing(b["id"])["status"] == "pending_pay"


def _signed(payload: bytes, secret: str) -> str:
    t = int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def test_webhook_signature_and_fulfillment(monkeypatch):
    secret = "whsec_test_dummy"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    u = _user("vend4@x.com")
    l = _pending_listing(u, sid="cs_hook", cents=5000)
    event = {"id": "evt_1", "object": "event", "type": "checkout.session.completed",
             "data": {"object": {"object": "checkout.session",
                                 **_sess("cs_hook", "publish", l["id"], 5000)}}}
    body = json.dumps(event).encode()
    r = client.post("/stripe/webhook", content=body,
                    headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 400
    assert storage.get_listing(l["id"])["status"] == "pending_pay"
    r = client.post("/stripe/webhook", content=body,
                    headers={"stripe-signature": _signed(body, secret)})
    assert r.status_code == 200 and r.json()["applied"] is True
    assert storage.get_listing(l["id"])["status"] == "active"


def test_webhook_disabled_without_secret(monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    assert client.post("/stripe/webhook", content=b"{}").status_code == 503


# ------------------------------------------------------------ rate limits ----

def test_login_rate_limit():
    c = TestClient(main.app)
    codes = [c.post("/login", data={"email": f"x{i}@y.com", "password": "malmalmal"}).status_code
             for i in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_login_rate_limit_per_account():
    c = TestClient(main.app)
    codes = []
    for i in range(9):
        c.headers["cf-connecting-ip"] = f"10.0.0.{i}"
        codes.append(c.post("/login", data={"email": "victima@y.com", "password": "malmalmal"}).status_code)
    assert codes[-1] == 429


def test_admin_lockout_and_constant_time():
    c = TestClient(main.app)
    for _ in range(5):
        r = c.post("/admin/entrar", data={"password": "incorrecta"})
        assert "Clave incorrecta" in r.text
    r = c.post("/admin/entrar", data={"password": "clave-admin-de-prueba-larga"},
               follow_redirects=False)
    assert r.status_code == 429 and main.ADMIN_COOKIE not in r.cookies


def test_admin_login_ok():
    c = TestClient(main.app)
    r = c.post("/admin/entrar", data={"password": "clave-admin-de-prueba-larga"},
               follow_redirects=False)
    assert r.status_code == 303 and r.cookies.get(main.ADMIN_COOKIE)


def test_admin_refused_without_env_in_prod(monkeypatch):
    import config
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    assert config.admin_password() == ""
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "corta")
    assert config.admin_password() == ""


def test_signup_and_forgot_rate_limit():
    c = TestClient(main.app)
    codes = [c.post("/registro", data={"name": "A", "email": f"r{i}@y.com",
                                         "password": "clave-larga-1"}, follow_redirects=False).status_code
             for i in range(6)]
    assert codes[-1] == 429
    codes = [c.post("/olvide", data={"email": f"f{i}@y.com"}).status_code for i in range(6)]
    assert codes[-1] == 429


def test_chat_rate_limit():
    seller = _user("sell-chat@x.com")
    buyer = _user("buy-chat@x.com", kyc=False)
    l = storage.create_listing(user_id=seller["id"], title="Rio", brand="Kia", model="Rio",
                               year=2018, price=5000, phone="1", status="active")
    convo = storage.get_or_create_conversation(l["id"], buyer["id"], seller["id"])
    c = _login_client(buyer)
    codes = [c.post(f"/api/c/{convo['id']}/mensaje", data={"body": f"hola {i}"}).status_code
             for i in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429


def test_report_rate_limit_per_listing():
    seller = _user("sell-rep@x.com")
    l = storage.create_listing(user_id=seller["id"], title="Golf", brand="VW", model="Golf",
                               year=2015, price=5000, phone="1", status="active")
    c = TestClient(main.app)
    assert c.post(f"/listing/{l['id']}/reportar", data={"reason": "estafa"}).status_code == 200
    assert c.post(f"/listing/{l['id']}/reportar", data={"reason": "estafa"}).status_code == 429


# ------------------------------------------------------------ cuentas ----

def test_password_min_length():
    with pytest.raises(ValueError):
        storage.create_user(email="corta@x.com", password="1234567", name="A")


def test_reset_invalidates_sessions():
    u = _user("reset@x.com", kyc=False)
    tok = storage.create_session(u["id"])
    storage.set_password(u["id"], "otra-clave-larga")
    assert storage.user_from_session(tok) is None


def test_oauth_does_not_link_unverified_account():
    storage.create_user(email="pre@x.com", password=PWD, name="Atacante")
    with pytest.raises(storage.UnverifiedAccountError):
        storage.upsert_oauth_user(email="pre@x.com", name="V", provider="google", oauth_id="g1")
    _user("ok-oauth@x.com", kyc=False)
    user, new = storage.upsert_oauth_user(email="ok-oauth@x.com", name="V",
                                          provider="google", oauth_id="g2")
    assert user and not new


def test_logout_requires_post():
    u = _user("logout@x.com", kyc=False)
    c = _login_client(u)
    tok = c.cookies.get(main.SESSION_COOKIE)
    c.get("/salir")
    assert storage.user_from_session(tok) is not None
    c.post("/salir", follow_redirects=False)
    assert storage.user_from_session(tok) is None


def test_private_docs_owner_or_admin_only():
    import os
    u = _user("docs@x.com")
    l = _pending_listing(u, sid="cs_docs")
    fname = f"{l['id']}_{'a' * 12}.jpg"
    with open(os.path.join(main.PRIVATE_DIR, fname), "wb") as f:
        f.write(b"\xff\xd8\xff" + b"0" * 100)
    assert TestClient(main.app).get(f"/privado/{fname}").status_code == 404
    other = _login_client(_user("otro@x.com", kyc=False))
    assert other.get(f"/privado/{fname}").status_code == 404
    assert _login_client(u).get(f"/privado/{fname}").status_code == 200
    assert TestClient(main.app).get("/privado/..%2Fkyc%2F1_id.jpg").status_code == 404


def test_account_deletion_removes_listings():
    u = _user("borrar@x.com")
    l = storage.create_listing(user_id=u["id"], title="Borrar", brand="Ford", model="Ka",
                               year=2012, price=2000, phone="1", status="active")
    c = _login_client(u)
    c.post("/eliminar-cuenta", follow_redirects=False)
    assert storage.get_listing(l["id"]) is None and storage.get_user(u["id"]) is None


def test_email_html_is_escaped():
    import email_utils
    html = email_utils._html("T", [email_utils.esc('<a href="https://evil">x</a>')], "B", "https://s")
    assert "<a href=\"https://evil\">" not in html and "&lt;a href=" in html


def test_upload_size_limit():
    import asyncio
    import io
    from starlette.datastructures import UploadFile
    big = UploadFile(file=io.BytesIO(b"\xff\xd8\xff" + b"0" * (main.MAX_UPLOAD_BYTES + 10)),
                     filename="a.jpg")
    with pytest.raises(ValueError):
        asyncio.run(main._save_photo(1, big))


# ---------------------------------------------------------------- sitemap ----

import re  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
IMG = "{http://www.google.com/schemas/sitemap-image/1.1}"


def _locs(xml_text, tag="url"):
    root = ET.fromstring(xml_text.encode())
    return root, [e.find(f"{SM}loc").text for e in root.findall(f"{SM}{tag}")]


def _get_path(url):
    from urllib.parse import urlsplit
    p = urlsplit(url)
    return p.path + (("?" + p.query) if p.query else "")


def test_sitemap_index_and_pages_valid():
    seller = _user("sm-seller@x.com")
    l = storage.create_listing(user_id=seller["id"], title="Hilux 2020", brand="Toyota",
                               model="Hilux", year=2020, price=30000, city="Maracaibo",
                               state="Zulia", phone="1", status="active")
    storage.add_listing_photo(l["id"], "/static/uploads/foto.jpg", 0)
    r = client.get("/sitemap.xml")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    root, subs = _locs(r.text, "sitemap")
    assert root.tag == f"{SM}sitemapindex"
    assert any(s.endswith("/sitemap-paginas.xml") for s in subs)
    assert any(s.endswith("/sitemap-carros.xml") for s in subs)
    for e in root.findall(f"{SM}sitemap"):
        assert len(e.find(f"{SM}lastmod").text) == 10

    _, pages = _locs(client.get("/sitemap-paginas.xml").text)
    _, cars_root_text = None, client.get("/sitemap-carros.xml").text
    croot, cars = _locs(cars_root_text)
    all_urls = pages + cars
    assert all("www." not in u and "?" not in u for u in all_urls)
    assert any(u.endswith("/estados/zulia") for u in pages)
    assert not any(u.endswith("/estados/amazonas") for u in pages)  # sin anuncios
    assert any(u.endswith(f"-{l['id']}") for u in cars)
    assert croot.find(f"{SM}url/{IMG}image/{IMG}loc").text.endswith("/static/uploads/foto.jpg")
    for u in pages + cars:
        assert client.get(_get_path(u), follow_redirects=False).status_code == 200, u
    for e in croot.findall(f"{SM}url"):
        assert re.fullmatch(r"20\d\d-\d\d-\d\d", e.find(f"{SM}lastmod").text)


def test_sitemap_excludes_demo_and_pending():
    u = _user("sm-pend@x.com")
    p = _pending_listing(u, sid="cs_sm")
    text = client.get("/sitemap-carros.xml").text + client.get("/sitemap-paginas.xml").text
    assert f"-{p['id']}<" not in text
    for d in storage.browse_listings(limit=500, include_demo=True):
        if d.get("is_demo"):
            assert main.listing_slug(d) not in text


def test_empty_area_pages_noindex_and_filtered_home():
    r = client.get("/estados/amazonas")
    assert r.status_code == 200 and 'name="robots" content="noindex,follow"' in r.text
    r = client.get("/carros/puerto-ayacucho")
    if r.status_code == 200:
        assert 'content="noindex,follow"' in r.text
    assert 'content="noindex,follow"' in client.get("/?q=toyota").text
    assert 'name="robots"' not in client.get("/").text


def test_robots_txt():
    t = client.get("/robots.txt").text
    for p in ("/admin", "/privado/", "/mensajes", "/c/", "/api/", "/*?"):
        assert f"Disallow: {p}\n" in t
    assert "Sitemap: https://motorcriollo.store/sitemap.xml" in t
    assert "Disallow: /carro" not in t and "Disallow: /blog" not in t
