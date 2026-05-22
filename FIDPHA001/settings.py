from pathlib import Path
from django.templatetags.static import static
from django.urls import reverse_lazy
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-84==t^=mjl&51p8p)x)w%+=j=vd4=548f4q!c2snwih0a%qsnj')

DEBUG = config('DEBUG', default=False, cast=bool)

# ---------------------------------------------------------------------------
# Sentry — initialized as early as possible so it captures errors raised
# during the rest of settings.py loading (e.g. broken DB config, missing
# secrets). When SENTRY_DSN is empty, Sentry is silently disabled.
# ---------------------------------------------------------------------------
_SENTRY_DSN = config('SENTRY_DSN', default='')
if _SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[DjangoIntegration()],
        # Performance tracing: 100% in dev (cheap, low traffic),
        # 10% in production (sample to control event volume + cost).
        traces_sample_rate=1.0 if DEBUG else 0.1,
        # Code profiling: find slow code paths. Same sampling rule.
        profiles_sample_rate=1.0 if DEBUG else 0.1,
        # GDPR-safe: no PII (cookies, IPs, user data) sent by default.
        # Override per-event with sentry_sdk.set_user(...) when needed.
        send_default_pii=False,
        # Tag every event so we can filter dev vs staging vs production.
        environment=config('SENTRY_ENVIRONMENT', default='dev' if DEBUG else 'production'),
        # Optional: release version (set by CI/CD via git SHA).
        release=config('SENTRY_RELEASE', default=None),
    )

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*,khalidbrx.pythonanywhere.com', cast=Csv())

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "fidpha.apps.FidphaConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",


    "rest_framework",
    "api",
    "control.apps.ControlConfig",
    "sales",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise must come right after SecurityMiddleware. It serves
    # static files efficiently in production (compressed + cached),
    # eliminating the need for a separate web server like Nginx.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "FIDPHA001.urls"

LOGIN_URL = "/portal/login/"
LOGIN_REDIRECT_URL = "/portal/dashboard/"
LOGOUT_REDIRECT_URL = "/portal/login/"

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "OAUTH_PKCE_ENABLED": True,
    }
}

SOCIALACCOUNT_LOGIN_ON_GET = True
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = "email"
SOCIALACCOUNT_AUTO_SIGNUP = False
SOCIALACCOUNT_ADAPTER = "fidpha.adapters.FIDPHASocialAccountAdapter"
ACCOUNT_ADAPTER = "fidpha.adapters.FIDPHAAccountAdapter"

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='buarramoukhalid@gmail.com')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='WinInPharma <buarramoukhalid@gmail.com>')

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "FIDPHA001.wsgi.application"

# DB_BACKEND controls which database is used: sqlite | local | neon
DB_BACKEND = config('DB_BACKEND', default='sqlite')

if DB_BACKEND == 'local':
    DATABASES = {
        'default': {
            'ENGINE':   'django.db.backends.postgresql',
            'NAME':     config('LOCAL_DB_NAME'),
            'USER':     config('LOCAL_DB_USER'),
            'PASSWORD': config('LOCAL_DB_PASSWORD'),
            'HOST':     config('LOCAL_DB_HOST', default='localhost'),
            'PORT':     config('LOCAL_DB_PORT', default='5432'),
            'OPTIONS':  {'sslmode': 'prefer'},
        }
    }
elif DB_BACKEND == 'neon':
    DATABASES = {
        'default': {
            'ENGINE':   'django.db.backends.postgresql',
            'NAME':     config('NEON_DB_NAME'),
            'USER':     config('NEON_DB_USER'),
            'PASSWORD': config('NEON_DB_PASSWORD'),
            'HOST':     config('NEON_DB_HOST'),
            'PORT':     config('NEON_DB_PORT', default='5432'),
            'OPTIONS':  {'sslmode': 'require'},
        }
    }
else:  # sqlite (default)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME':   BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Cache + Sessions
# When REDIS_URL is set: shared Redis cache (works across Gunicorn workers
# and multiple server instances) + cached-DB sessions (fast reads from
# Redis, durable writes to DB — survives Redis outages).
# When REDIS_URL is empty: fall back to local in-memory cache + DB sessions.
# Local fallback is safe for single-process dev but won't share state.
# ---------------------------------------------------------------------------
REDIS_URL = config('REDIS_URL', default='')

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                # If Redis is unreachable, raise the connection error instead
                # of silently swallowing it (better for catching outages).
                "IGNORE_EXCEPTIONS": False,
            },
            "KEY_PREFIX": "wininpharma",
            "TIMEOUT": 300,  # default 5min; override per cache.set() call.
        }
    }
    # cached_db: read from cache (fast), write to both cache + DB (durable).
    # If Redis fails, falls back to DB only — no session loss.
    SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
    SESSION_CACHE_ALIAS = "default"
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
    # Leave SESSION_ENGINE at Django's default ("db") — safe for local dev.

# ---------------------------------------------------------------------------
# Logging
# In DEBUG: human-readable lines to console (easy to scan during dev).
# In prod : structured JSON to stdout (queryable by Sentry / Better Stack).
# Application code uses logging.getLogger("wininpharma.<area>") e.g.
#   logger = logging.getLogger("wininpharma.api")
#   logger.info("Batch accepted", extra={"batch_id": ..., "rows": ...})
# ---------------------------------------------------------------------------
LOG_LEVEL = config("LOG_LEVEL", default="INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "fmt": "%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(funcName)s %(lineno)d",
            "rename_fields": {
                "asctime": "time",
                "levelname": "level",
                "name": "logger",
            },
        },
        "verbose": {
            "format": "[{asctime}] {levelname:8} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose" if DEBUG else "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        # Django framework — silence the chatter, keep INFO and above.
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # 4xx/5xx HTTP errors — surface them clearly.
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        # Our application namespace. All app code does
        # logging.getLogger("wininpharma.<area>") to land here.
        "wininpharma": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Security headers
# These tell browsers to enforce safety policies. HTTPS-related headers are
# gated on `not DEBUG` so local HTTP dev still works unchanged.
# CSP (Content-Security-Policy) is intentionally deferred until after the
# React migration, since current templates use inline <script> blocks.
# ---------------------------------------------------------------------------

# Browser respects our Content-Type header — prevents MIME-sniffing attacks
SECURE_CONTENT_TYPE_NOSNIFF = True

# Enable browser's legacy XSS filter (defense in depth, low cost)
SECURE_BROWSER_XSS_FILTER = True

# Don't leak full URL as referrer to other origins
SECURE_REFERRER_POLICY = "same-origin"

# Block embedding in iframes — prevents clickjacking
X_FRAME_OPTIONS = "DENY"

# HTTPS-only settings — applied only in production (DEBUG=False).
# Skipped in CI even with DEBUG=False, because the Django test client and
# Playwright's live_server both speak plain HTTP. The CI env var is set in
# .github/workflows/ci.yml.
_IS_CI = config("CI", default=False, cast=bool)
if not DEBUG and not _IS_CI:
    # Redirect any HTTP request to HTTPS
    SECURE_SSL_REDIRECT = True
    # Tell browsers "use HTTPS only" for 1 year (with subdomains, preload-ready)
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # Trust X-Forwarded-Proto header from reverse proxy (Railway, Render, Nginx)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Cookies only sent over HTTPS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("fr", "Français"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = 'Africa/Casablanca'
USE_TZ = True
USE_I18N = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Static file storage — WhiteNoise's compressed + manifest backend.
# - Generates gzip/brotli versions of every CSS/JS file at collectstatic time.
# - Adds a content hash to filenames (e.g. portal.abc123.css) for unbreakable caching.
# - In DEBUG mode, falls back to standard Django dev behavior automatically.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

UNFOLD = {
    "SITE_TITLE": "WinInPharma Admin",
    "SITE_HEADER": "WinInPharma",
    "SITE_URL": "/",
    "SITE_ICON": None,
    "SITE_SYMBOL": "medication",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "STYLES": [
        lambda request: static("admin.css"),
    ],
    "SCRIPTS": [
        lambda request: static("admin/account_form.js"),
    ],
    "COLORS": {
        "primary": {
            "50": "240 249 255",
            "100": "224 242 254",
            "200": "186 230 253",
            "300": "125 211 252",
            "400": "56 189 248",
            "500": "14 165 233",
            "600": "27 103 155",
            "700": "15 82 125",
            "800": "12 63 96",
            "900": "8 44 68",
            "950": "5 28 44",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Authentication",
                "icon": "lock",
                "permission": lambda request: request.user.is_superuser,
                "items": [
                    {
                        "title": "Users",
                        "icon": "person",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                        "permission": lambda request: request.user.has_perm("auth.view_user"),
                        "badge": "fidpha.utils.users_badge",
                    },
                    {
                        "title": "Groups",
                        "icon": "group",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                        "permission": lambda request: request.user.has_perm("auth.view_group"),
                    },
                ],
            },
            {
                "title": "WinInPharma",
                "icon": "local_pharmacy",
                "items": [
                    {
                        "title": "Accounts",
                        "icon": "store",
                        "link": reverse_lazy("admin:fidpha_account_changelist"),
                        "permission": lambda request: request.user.has_perm("fidpha.view_account"),
                        "badge": "fidpha.utils.accounts_badge",
                    },
                    {
                        "title": "Contracts",
                        "icon": "description",
                        "link": reverse_lazy("admin:fidpha_contract_changelist"),
                        "permission": lambda request: request.user.has_perm("fidpha.view_contract"),
                        "badge": "fidpha.utils.contracts_badge",
                    },
                    {
                        "title": "Products",
                        "icon": "medication",
                        "link": reverse_lazy("admin:fidpha_product_changelist"),
                        "permission": lambda request: request.user.has_perm("fidpha.view_product"),
                        "badge": "fidpha.utils.products_badge",
                    },
                ],
            },
            {
                "title": "API",
                "icon": "api",
                "permission": lambda request: request.user.is_superuser,
                "items": [
                    {
                        "title": "API Tokens",
                        "icon": "key",
                        "link": reverse_lazy("admin:api_apitoken_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                ],
            },
            {
                "title": "Sites",
                "icon": "language",
                "permission": lambda request: request.user.is_superuser,
                "items": [
                    {
                        "title": "Sites",
                        "icon": "public",
                        "link": reverse_lazy("admin:sites_site_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                ],
            },
            {
                "title": "Social Accounts",
                "icon": "connect_without_contact",
                "permission": lambda request: request.user.is_superuser,
                "items": [
                    {
                        "title": "Social Accounts",
                        "icon": "manage_accounts",
                        "link": reverse_lazy("admin:socialaccount_socialaccount_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": "Social Applications",
                        "icon": "apps",
                        "link": reverse_lazy("admin:socialaccount_socialapp_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": "Social Tokens",
                        "icon": "token",
                        "link": reverse_lazy("admin:socialaccount_socialtoken_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                ],
            },
        ],
    },
}



REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "api.authentication.APITokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "api.permissions.HasAPIToken",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "api.throttles.APITokenThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "api_token": "1000/hour",
    },
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],

    "EXCEPTION_HANDLER": "api.views.custom_exception_handler",
}


if DEBUG:
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] += [
        "rest_framework.renderers.BrowsableAPIRenderer",
    ]


# ---------------------------------------------------------------------------
# Test runner
# Uses a custom runner that appends a log entry to test_log.txt after
# every test run. The log file is excluded from version control (.gitignore).
# ---------------------------------------------------------------------------

TEST_RUNNER = "FIDPHA001.test_runner.LoggingTestRunner"