import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "core",
    "catalog",
    "marketplace",
    "sellerportal",
    "facility",
    "greencredits",
    "grading",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "loop"),
        "USER": os.environ.get("POSTGRES_USER", "loop"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "core.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 24,
}

# Sessions/CSRF: SPA and API are same-origin behind nginx, so defaults work.
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o
]
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"  # scale: swap cache backend only

# --- Production hardening (no-ops in local dev) ---
# Behind nginx/ALB/CloudFront the original scheme arrives in X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if os.environ.get("SECURE_COOKIES", "0") == "1":  # set once site is on HTTPS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# Cache: LocMem now; set REDIS_URL to switch (sessions follow automatically).
_redis_url = os.environ.get("REDIS_URL", "")
if _redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
        }
    }
else:
    CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Media storage: local volume by default, S3 when USE_S3=1 (scale: env only) ---
USE_S3 = os.environ.get("USE_S3", "0") == "1"
if USE_S3:
    AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME", "")
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "ap-south-1")
    AWS_S3_CUSTOM_DOMAIN = os.environ.get("AWS_S3_CUSTOM_DOMAIN", "")  # e.g. CloudFront
    AWS_DEFAULT_ACL = None              # bucket owns objects; access via policy
    AWS_QUERYSTRING_AUTH = False        # clean public URLs (bucket policy allows read)
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    MEDIA_URL = (
        f"https://{AWS_S3_CUSTOM_DOMAIN}/"
        if AWS_S3_CUSTOM_DOMAIN
        else f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"
    )
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- AI service (real, behind a toggle) ---
AI_MOCK = os.environ.get("AI_MOCK", "1") == "1"
AI_SERVICE_URL = os.environ.get("AI_SERVICE_URL", "")
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_TIMEOUT_SECONDS = float(os.environ.get("AI_TIMEOUT_SECONDS", "5"))

# --- Loop business knobs ---
STORAGE_DAILY_RATE_DEFAULT = 5          # ₹/day
STORAGE_DAILY_RATE_BY_CATEGORY = {      # override per category
    "electronics": 8,
    "apparel": 3,
    "footwear": 4,
}
PRICE_STEPDOWN_EVERY_DAYS = 7
PRICE_STEPDOWN_PCT = 10                 # −10% per step, floor band_lo

# --- Return window (block returns past the window; offer resell instead) ---
RETURN_WINDOW_DAYS = int(os.environ.get("RETURN_WINDOW_DAYS", "7"))
RETURN_WINDOW_DAYS_BY_CATEGORY = {      # override per category
    "electronics": 7,
    "apparel": 14,
    "footwear": 14,
}

# --- Celery (async return grading workers) ---
# Reuses Redis. Broker/result default to the shared REDIS_URL, then to the
# compose "redis" service. ALWAYS_EAGER runs tasks inline (tests / no broker).
CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", _redis_url or "redis://redis:6379/0"
)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "0") == "1"
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# --- AI return grading ---
# Multi-source grader: VLM (OpenAI-compatible) + perceptual-hash similarity +
# EXIF metadata + buyer history. "auto" picks gemini when a key is present,
# else the deterministic mock so local/dev never breaks.
GRADING_VLM_PROVIDER = os.environ.get("GRADING_VLM_PROVIDER", "auto")
GRADING_EMBEDDING_PROVIDER = os.environ.get("GRADING_EMBEDDING_PROVIDER", "phash")
GRADING_VLM_TIMEOUT = float(os.environ.get("GRADING_VLM_TIMEOUT", "30"))
GRADING_VLM_MAX_IMAGES = int(os.environ.get("GRADING_VLM_MAX_IMAGES", "6"))
GRADING_REFERENCE_CACHE_TTL = int(os.environ.get("GRADING_REFERENCE_CACHE_TTL", "86400"))

# OpenAI-compatible LLM providers. Adding a provider = a config entry, not code.
# Gemini is reached via Google's OpenAI-compatibility endpoint.
LLM_PROVIDERS = {
    "gemini": {
        "base_url": os.environ.get(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ),
        "api_key": os.environ.get("GEMINI_API_KEY", ""),
        "model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        "requires_key": True,
    },
    "openai": {
        "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "api_key": os.environ.get("OPENAI_API_KEY", ""),
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "requires_key": True,
    },
    "modal": {  # self-hosted vLLM speaks the OpenAI protocol — fill when deployed
        "base_url": os.environ.get("MODAL_BASE_URL", ""),
        "api_key": os.environ.get("MODAL_API_KEY", ""),
        "model": os.environ.get("MODAL_MODEL", ""),
        "requires_key": False,
    },
}
