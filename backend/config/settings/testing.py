from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "insecure-test-only-key-that-is-long-enough-for-hmac"  # noqa: S105
SIMPLE_JWT["SIGNING_KEY"] = SECRET_KEY  # noqa: F405
ALLOWED_HOSTS = ["testserver", "localhost"]

# Fast hasher: tests only. Production uses Argon2.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Throttle rates are exercised explicitly in dedicated tests.
REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100000/min",
        "user": "100000/min",
        "login": "100000/min",
        "register": "100000/min",
        "password_reset": "100000/min",
        "verification": "100000/min",
        "geo": "100000/min",
        "price_write": "100000/min",
        "contribution": "100000/min",
    },
}
