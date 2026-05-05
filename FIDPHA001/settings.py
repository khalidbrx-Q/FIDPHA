from pathlib import Path
from django.templatetags.static import static
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-84==t^=mjl&51p8p)x)w%+=j=vd4=548f4q!c2snwih0a%qsnj"

DEBUG = False ################## CHANGE THIS TO False FOR PRODUCTION

ALLOWED_HOSTS = ['*', 'khalidbrx.pythonanywhere.com']

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
EMAIL_HOST_USER = 'buarramoukhalid@gmail.com'
EMAIL_HOST_PASSWORD = 'gbxz sdba xxxh meme'
DEFAULT_FROM_EMAIL = 'WinInPharma <buarramoukhalid@gmail.com>'

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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

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