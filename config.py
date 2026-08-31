import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Disco persistente en Render: MOTORCRIOLLO_DATA=/var/data
DATA_ROOT = os.environ.get("MOTORCRIOLLO_DATA", "").rstrip("/\\")
DATA_DIR = os.path.join(DATA_ROOT, "data") if DATA_ROOT else os.path.join(BASE_DIR, "data")
UPLOAD_DIR = (
    os.path.join(DATA_ROOT, "uploads")
    if DATA_ROOT
    else os.path.join(BASE_DIR, "static", "uploads")
)
DEMO_DIR = os.path.join(BASE_DIR, "static", "demo")
KYC_DIR = os.path.join(DATA_DIR, "kyc")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DEMO_DIR, exist_ok=True)
os.makedirs(KYC_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "motorcriollo.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
PERSISTENT = bool(DATABASE_URL or DATA_ROOT)
PUBLIC_BASE_URL = os.environ.get("MOTORCRIOLLO_PUBLIC_URL", "").rstrip("/")
if not PUBLIC_BASE_URL and os.environ.get("RENDER"):
    PUBLIC_BASE_URL = "https://www.motorcriollo.store"
SECRET = os.environ.get("MOTORCRIOLLO_SECRET", "motorcriollo-dev-cambia-esto")
ADMIN_PASSWORD = (
    os.environ.get("MOTORCRIOLLO_ADMIN") or os.environ.get("ADMIN_PASSWORD") or ""
).strip() or (
    SECRET if SECRET != "motorcriollo-dev-cambia-esto" else ""
)
PORT = int(os.environ.get("PORT") or os.environ.get("MOTORCRIOLLO_PORT", "8789"))
SESSION_COOKIE = "mc_session"
OAUTH_STATE_COOKIE = "mc_oauth"
SESSION_DAYS = 30
MAX_PHOTOS = 8
COMMISSION_USD = int(os.environ.get("MOTORCRIOLLO_COMMISSION") or "20")
PAY_INFO = (
    os.environ.get("MOTORCRIOLLO_PAY_INFO")
    or "Paga la comisión a MotorCriollo por Zelle o Pago Móvil y sube el comprobante. "
       "Administración confirma el pago y se cierra la venta."
)
try:
    from config_local import COMMISSION_USD as _CUSD

    COMMISSION_USD = int(_CUSD or COMMISSION_USD)
except Exception:
    pass
try:
    from config_local import PAY_INFO as _PAY

    if _PAY:
        PAY_INFO = str(_PAY)
except Exception:
    pass

GOOGLE_CLIENT_ID = os.environ.get("MOTORCRIOLLO_GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("MOTORCRIOLLO_GOOGLE_CLIENT_SECRET", "")
APPLE_CLIENT_ID = os.environ.get("MOTORCRIOLLO_APPLE_CLIENT_ID", "")
APPLE_TEAM_ID = os.environ.get("MOTORCRIOLLO_APPLE_TEAM_ID", "")
APPLE_KEY_ID = os.environ.get("MOTORCRIOLLO_APPLE_KEY_ID", "")
APPLE_PRIVATE_KEY = os.environ.get("MOTORCRIOLLO_APPLE_PRIVATE_KEY", "")

try:
    from config_local import GOOGLE_CLIENT_ID as _G1

    GOOGLE_CLIENT_ID = _G1 or GOOGLE_CLIENT_ID
except ImportError:
    pass
try:
    from config_local import GOOGLE_CLIENT_SECRET as _G2

    GOOGLE_CLIENT_SECRET = _G2 or GOOGLE_CLIENT_SECRET
except ImportError:
    pass
try:
    from config_local import APPLE_CLIENT_ID as _A1

    APPLE_CLIENT_ID = _A1 or APPLE_CLIENT_ID
except ImportError:
    pass
try:
    from config_local import APPLE_TEAM_ID as _A2

    APPLE_TEAM_ID = _A2 or APPLE_TEAM_ID
except ImportError:
    pass
try:
    from config_local import APPLE_KEY_ID as _A3

    APPLE_KEY_ID = _A3 or APPLE_KEY_ID
except ImportError:
    pass
try:
    from config_local import APPLE_PRIVATE_KEY as _A4

    APPLE_PRIVATE_KEY = _A4 or APPLE_PRIVATE_KEY
except ImportError:
    pass

try:
    from config_local import APPLE_PRIVATE_KEY_FILE as _AF

    if _AF and os.path.exists(_AF):
        with open(_AF, encoding="utf-8") as f:
            APPLE_PRIVATE_KEY = f.read()
except ImportError:
    pass


def admin_password() -> str:
    if ADMIN_PASSWORD:
        return ADMIN_PASSWORD
    if os.environ.get("RENDER"):
        return ""
    return "criolloadmin"


def google_enabled() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def stripe_secret() -> str:
    k = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()
    if k:
        return k
    try:
        from config_local import STRIPE_SECRET_KEY as _SK

        return str(_SK or "").strip()
    except Exception:
        return ""


def stripe_enabled() -> bool:
    k = stripe_secret()
    return k.startswith("sk_test_") or k.startswith("sk_live_")


def stripe_mode() -> str | None:
    k = stripe_secret()
    if k.startswith("sk_live_"):
        return "live"
    if k.startswith("sk_test_"):
        return "test"
    return None


def apple_enabled() -> bool:
    return bool(APPLE_CLIENT_ID and APPLE_TEAM_ID and APPLE_KEY_ID and APPLE_PRIVATE_KEY)
