from .base import *  # noqa: F403
from .base import SECRET_KEY as _BASE_SECRET_KEY

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "10.0.2.2"]  # 10.0.2.2: Android emulator -> host
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

SECRET_KEY = _BASE_SECRET_KEY or "insecure-dev-only-key-not-for-production-use-0123456789"
if not _BASE_SECRET_KEY:
    SIMPLE_JWT["SIGNING_KEY"] = SECRET_KEY  # noqa: F405
