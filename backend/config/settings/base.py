"""Settings shared by every environment. Secrets come from the environment only."""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

from config.gis import gis_library_settings

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BASE_DIR.parent

# Local convenience only. Production must receive real environment variables, so a stray
# .env file can never mask a missing secret there.
if not os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(".production"):
    load_dotenv(REPO_ROOT / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS: list[str] = env_list("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    # Local
    "apps.core",
    "apps.users",
    "apps.audit",
    "apps.merchants",
    "apps.stores",
    "apps.products",
    "apps.prices",
    "apps.promotions",
    "apps.recommendations",
    "apps.shopping_lists",
    "apps.shopping_cart",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        **dj_database_url.parse(
            os.environ.get("DATABASE_URL", "postgres://ondetabarato@localhost:5432/ondetabarato"),
            conn_max_age=60,
        ),
        "ENGINE": "django.contrib.gis.db.backends.postgis",
    }
}
# Local dev: the app role is not a superuser and cannot CREATE EXTENSION, so test databases
# are cloned from a template that already has PostGIS (see docs/DEVELOPMENT.md).
if os.environ.get("DB_TEST_TEMPLATE"):
    DATABASES["default"]["TEST"] = {"TEMPLATE": os.environ["DB_TEST_TEMPLATE"]}

# GeoDjango libraries: only set on Windows dev machines (Linux uses system packages).
_gis = gis_library_settings()
if _gis:
    GDAL_LIBRARY_PATH = _gis["GDAL_LIBRARY_PATH"]
    GEOS_LIBRARY_PATH = _gis["GEOS_LIBRARY_PATH"]

AUTH_USER_MODEL = "users.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = os.environ.get("TIME_ZONE", "America/Fortaleza")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Cache (throttling, lockout). Redis in production. ---
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --- E-mail ---
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "OndeTáBarato <no-reply@localhost>")

# --- CORS ---
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_ALL_ORIGINS = False

# --- REST framework ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "240/min",
        "login": "10/min",
        "register": "10/hour",
        "password_reset": "5/hour",
        "verification": "5/hour",
        "geo": "120/min",
        "price_write": "60/hour",
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "apps.core.api.exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get("JWT_REFRESH_DAYS", "14"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.environ.get("JWT_SECRET", "") or SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "OndeTáBarato API",
    "DESCRIPTION": "API do assistente inteligente de compras OndeTáBarato.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # Stable, readable enum names in the generated API schema (and future client code).
    "ENUM_NAME_OVERRIDES": {
        "RoleEnum": "apps.users.models.Role.choices",
        "MemberRoleEnum": "apps.merchants.models.MemberRole.choices",
        "VerificationStatusEnum": "apps.merchants.models.VerificationStatus.choices",
        "StoreStatusEnum": "apps.stores.models.StoreStatus.choices",
        "StoreTypeEnum": "apps.stores.models.StoreType.choices",
        "PaymentConditionEnum": "apps.prices.models.PaymentCondition.choices",
        "ShopperPaymentEnum": "apps.recommendations.serializers.SHOPPER_PAYMENT_CHOICES",
        "PriceSourceEnum": "apps.prices.models.PriceSource.choices",
    },
}

# --- Project rules ---
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60
EMAIL_VERIFICATION_MAX_AGE_SECONDS = 48 * 3600
PASSWORD_RESET_TIMEOUT = 1 * 3600  # Django's token generator setting (seconds)
# --- Prices (see docs/DATA_INTEGRITY.md) ---
PRICE_DEFAULT_TTL_HOURS = 168  # used when a product has no category
PRICE_DEDUP_HOURS = 6  # same price re-reported inside this window does not create a new row
PRICE_MAX_LISTED_AGE_DAYS = 90  # older observations stay in history but leave live listings
# Optional override of confidence weights: PRICE_CONFIDENCE = {"evidence_bonus": 0.1, ...}

# IP is personal data under LGPD: stored in AuditLog only when explicitly enabled.
AUDIT_STORE_IP = env_bool("AUDIT_STORE_IP", False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
        },
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "structured"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
