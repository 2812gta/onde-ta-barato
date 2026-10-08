import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]


def run_settings(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "SYSTEMROOT", "SystemRoot"}}
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
    env.update(extra_env)
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import config.settings.production"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


VALID = {
    "SECRET_KEY": "k" * 60,
    "JWT_SECRET": "j" * 40,
    "ALLOWED_HOSTS": "example.com",
    "DATABASE_URL": "postgres://u:p@localhost/db",
}


def test_valid_environment_loads():
    assert run_settings(VALID).returncode == 0


@pytest.mark.parametrize("missing", ["SECRET_KEY", "JWT_SECRET", "ALLOWED_HOSTS", "DATABASE_URL"])
def test_missing_required_setting_fails_fast(missing):
    result = run_settings({k: v for k, v in VALID.items() if k != missing})
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr


def test_short_secret_key_is_rejected():
    result = run_settings({**VALID, "SECRET_KEY": "short"})
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_local_dotenv_does_not_leak_into_production():
    """The repo-root .env (if present) must not satisfy production requirements."""
    result = run_settings({})
    assert result.returncode != 0
