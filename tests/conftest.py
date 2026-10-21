"""Tests en modo producción simulado (RENDER=1) con una base SQLite temporal."""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="mc-test-")
os.environ["MOTORCRIOLLO_DATA"] = _tmp
os.environ["RENDER"] = "1"
os.environ.pop("DATABASE_URL", None)
os.environ.pop("MOTORCRIOLLO_DEMO", None)
os.environ["MOTORCRIOLLO_ADMIN"] = "clave-admin-de-prueba-larga"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_dummy_for_tests"
os.environ.pop("SENDGRID_API_KEY", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_limits():
    from security import limiter

    limiter.reset()
    yield
    limiter.reset()
