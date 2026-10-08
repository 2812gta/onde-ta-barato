import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env_bool

DEBUG = False

if len(SECRET_KEY) < 50:  # noqa: F405
    raise ImproperlyConfigured("SECRET_KEY must be set (>= 50 chars) in production.")
if not os.environ.get("JWT_SECRET"):
    raise ImproperlyConfigured("JWT_SECRET must be set in production.")
if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production.")
if "DATABASE_URL" not in os.environ:
    raise ImproperlyConfigured("DATABASE_URL must be set in production.")

# HTTPS terminated by Nginx.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False  # enable only after confirming all subdomains are HTTPS
SILENCED_SYSTEM_CHECKS = ["security.W021"]  # preload is a deliberate, later decision
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

REDIS_URL = os.environ.get("REDIS_URL", "")
if REDIS_URL:
    CACHES = {  # noqa: F405
        "default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}
    }

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = True
