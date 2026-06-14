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
    "rerouting",
    "nextowner",
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

# --- Legacy mock AI (services/ai.py): deterministic, network-free helpers.
# Real image-aware grading/routing lives in the grading/ + rerouting/ apps
# (Gemini via LLM_PROVIDERS/GEMINI_API_KEY). AI_MOCK is kept for tests/back-compat.
AI_MOCK = os.environ.get("AI_MOCK", "1") == "1"

# --- Logging ---
# Without an explicit config Django suppresses INFO, so grading/rerouting
# decisions and provider fallbacks never reach `docker compose logs`. Surface
# our apps at INFO (override with LOG_LEVEL) while keeping third-party noise at
# WARNING.
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{levelname}] {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        name: {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False}
        for name in (
            "grading",
            "rerouting",
            "marketplace",
            "services",
            "facility",
            "core",
            "catalog",
            "greencredits",
            "nextowner",
        )
    },
}

# --- Loop business knobs ---
STORAGE_DAILY_RATE_DEFAULT = 5          # ₹/day
STORAGE_DAILY_RATE_BY_CATEGORY = {      # override per category
    "electronics": 8,
    "apparel": 3,
    "footwear": 4,
    "general": 5,
}
PRICE_STEPDOWN_EVERY_DAYS = 7
PRICE_STEPDOWN_PCT = 10                 # −10% per step, floor band_lo

# --- Return window (block returns past the window; offer resell instead) ---
RETURN_WINDOW_DAYS = int(os.environ.get("RETURN_WINDOW_DAYS", "7"))
RETURN_WINDOW_DAYS_BY_CATEGORY = {      # override per category
    "electronics": 7,
    "apparel": 14,
    "footwear": 14,
    "general": 7,
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
        # gemini-2.5-flash "thinks" by default (~30s grades). Grading is a
        # structured-extraction task, not deep reasoning, so cap it. "low" keeps
        # quality while cutting most of the latency; "none" disables thinking.
        "reasoning_effort": os.environ.get("GEMINI_REASONING_EFFORT", "low"),
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

# --- Rerouting (return disposition: RESELL / REFURBISH / P2P / DONATE) --------
# Decides what to do with a returned unit. Two strategies run in parallel: a
# deterministic Expected-Value optimizer and an LLM. The LLM is authoritative;
# EV is the fallback and always supplies the money breakdown. Reuses the same
# LLM_PROVIDERS table as grading; "mock" (or no key) -> EV result, no network.
REROUTING_LLM_PROVIDER = os.environ.get("REROUTING_LLM_PROVIDER", "auto")
REROUTING_LLM_TIMEOUT = float(os.environ.get("REROUTING_LLM_TIMEOUT", "20"))

# Logistics cost model. rate = RATE_PER_KM[size] * FRAG_MULT[fragility]; a return
# leg + an outbound resale leg are both charged at the inter-city distance, while
# P2P/DONATE stay in-city (LOCAL_KM). Big items need a truck => much higher /km.
REROUTING_RATE_PER_KM = {"small": 3.0, "big": 12.0}      # ₹ per km
REROUTING_FRAGILITY_MULT = {"rigid": 1.0, "delicate": 1.5}
REROUTING_LOCAL_KM = float(os.environ.get("REROUTING_LOCAL_KM", "15"))

# Value recovered per route. Repair restores condition but costs money; refurb
# and P2P resell at a discount (prototype assumption).
REROUTING_REPAIR_FACTOR = 0.4        # repair cost = (1-quality)*MRP*factor
REROUTING_REPAIR_MAX_PCT = 0.6       # cap repair at this fraction of MRP
REROUTING_REFURB_RESALE_PCT = 0.6    # refurbished resale price = pct * MRP
REROUTING_P2P_RESALE_PCT = 0.7       # P2P price = pct * est_value
REROUTING_REFURB_TARGET_QUALITY = 0.85  # quality a refurbished unit is restored to

# Risk adjustment: revenue is multiplied by a realization probability so quality
# and fraud actually matter (else resale/P2P always win). realize =
# sell_through(quality) * (1 - fraud_risk); donate has no revenue so it is the
# risk-immune floor.
REROUTING_SELL_THROUGH_BASE = 0.5    # realization at quality 0; ramps to 1.0 at quality 1
REROUTING_FRAUD_RESALE_RISK = 1.0    # how strongly fraud discounts resale revenue
REROUTING_REFURB_FRAUD_MITIGATION = 0.5  # inspection during refurb catches some fraud

# Return-prevention offer (keep-it: partial cash refund + green credits). Only
# offered when every route loses money and fraud is low. Cash-majority so the
# customer feels fairly compensated; credits are valued below par to the company
# because they guarantee a next order.
REROUTING_OFFER_FRAUD_MAX = 0.3      # don't bribe likely fraudsters
REROUTING_OFFER_MIN_QUALITY = 0.4    # item must be genuinely usable to keep
REROUTING_OFFER_CASH_SHARE = 0.6     # fraction of make-whole paid as cash (rest credits)
REROUTING_CREDIT_COST_FACTOR = 0.9   # ₹ cost to company per 1 credit of perceived value

# --- Next Best Owner (P2P resale matching + Dutch auction) --------------------
# A buyer resells an item; we embed products and buyer "demand" profiles, match
# the best-fit local buyers (bipartite top-k), then run a descending-price
# (Dutch) auction that widens to more buyers as the price steps down. Green
# credits sweeten resold purchases. Vectors are precomputed in parallel and
# cached so matching never re-embeds in the request path.
#
# Text embeddings: "local" = sentence-transformers MiniLM on CPU (worker); "mock"
# = deterministic hash vectors (no torch) for tests/offline. Falls back to mock
# if the model can't load. GPU/larger models via a hosted endpoint = future work.
NEXTOWNER_EMBEDDING_PROVIDER = os.environ.get("NEXTOWNER_EMBEDDING_PROVIDER", "local")
NEXTOWNER_EMBEDDING_MODEL = os.environ.get(
    "NEXTOWNER_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
NEXTOWNER_MOCK_EMBEDDING_DIM = int(os.environ.get("NEXTOWNER_MOCK_EMBEDDING_DIM", "64"))

# Match-score weights (sum ~1): semantic taste, category affinity, price fit,
# quality fit, green-buying propensity. Tunable without code changes.
NEXTOWNER_MATCH_WEIGHTS = {
    "semantic": float(os.environ.get("NEXTOWNER_W_SEMANTIC", "0.45")),
    "category": float(os.environ.get("NEXTOWNER_W_CATEGORY", "0.20")),
    "price": float(os.environ.get("NEXTOWNER_W_PRICE", "0.20")),
    "quality": float(os.environ.get("NEXTOWNER_W_QUALITY", "0.10")),
    "green": float(os.environ.get("NEXTOWNER_W_GREEN", "0.05")),
}
# Demo simplification: treat every buyer as same-locality (skip the city filter).
NEXTOWNER_SAME_LOCALITY_DEMO = os.environ.get("NEXTOWNER_SAME_LOCALITY_DEMO", "1") == "1"
NEXTOWNER_RECENCY_HALFLIFE_DAYS = float(os.environ.get("NEXTOWNER_RECENCY_HALFLIFE_DAYS", "45"))

# Dutch auction: start ABOVE fair value and step the price down each interval,
# alerting one more tier of buyers per step, until sold or the reserve / last
# tier is reached. The auction range (start premium .. reserve discount around
# the fair value) is intentionally WIDER than the pricing band below, so the
# price visibly descends across several steps rather than snapping to the floor.
NEXTOWNER_AUCTION_TIER_SIZE = int(os.environ.get("NEXTOWNER_AUCTION_TIER_SIZE", "3"))
NEXTOWNER_AUCTION_MAX_TIER = int(os.environ.get("NEXTOWNER_AUCTION_MAX_TIER", "4"))
NEXTOWNER_AUCTION_STEP_PCT = float(os.environ.get("NEXTOWNER_AUCTION_STEP_PCT", "12"))
NEXTOWNER_AUCTION_INTERVAL_SECONDS = int(
    os.environ.get("NEXTOWNER_AUCTION_INTERVAL_SECONDS", "60")
)
# Opening ask = est_value * (1 + start_premium); reserve = est_value * (1 - reserve_discount).
NEXTOWNER_AUCTION_START_PREMIUM = float(os.environ.get("NEXTOWNER_AUCTION_START_PREMIUM", "0.25"))
NEXTOWNER_AUCTION_RESERVE_DISCOUNT = float(
    os.environ.get("NEXTOWNER_AUCTION_RESERVE_DISCOUNT", "0.30")
)

# Pricing: est_value = P0 * [rho_min + (rho_max-rho_min)*quality^gamma]
#                         * (1-d_cat)^months * (1 - lambda*fraud)
# band = est_value * (1 ± band_width*(1-confidence)); the floor doubles as the
# seller's reserve (the auction never drops below it).
NEXTOWNER_PRICE_RHO_MIN = float(os.environ.get("NEXTOWNER_PRICE_RHO_MIN", "0.15"))
NEXTOWNER_PRICE_RHO_MAX = float(os.environ.get("NEXTOWNER_PRICE_RHO_MAX", "0.75"))
NEXTOWNER_PRICE_GAMMA = float(os.environ.get("NEXTOWNER_PRICE_GAMMA", "1.2"))
NEXTOWNER_PRICE_FRAUD_LAMBDA = float(os.environ.get("NEXTOWNER_PRICE_FRAUD_LAMBDA", "0.5"))
NEXTOWNER_PRICE_BAND_WIDTH = float(os.environ.get("NEXTOWNER_PRICE_BAND_WIDTH", "0.15"))
# Monthly depreciation rate by category (fraction/month); electronics fastest.
NEXTOWNER_DEPRECIATION_BY_CATEGORY = {
    "electronics": 0.05,
    "apparel": 0.03,
    "footwear": 0.035,
}
NEXTOWNER_DEPRECIATION_DEFAULT = float(os.environ.get("NEXTOWNER_DEPRECIATION_DEFAULT", "0.03"))

# Green credits for buying resold goods: a base award plus a bonus that grows as
# the Dutch price drops (rewards clearing slow inventory; eases resale hesitation).
NEXTOWNER_CREDIT_BASE = int(os.environ.get("NEXTOWNER_CREDIT_BASE", "20"))
NEXTOWNER_CREDIT_MAX_BONUS = int(os.environ.get("NEXTOWNER_CREDIT_MAX_BONUS", "40"))
NEXTOWNER_SELLER_RESELL_CREDIT = int(os.environ.get("NEXTOWNER_SELLER_RESELL_CREDIT", "30"))
