"""Base settings shared across environments.

Environment-specific files (development.py, production.py) override these.
Values that vary per environment or carry secrets MUST come from env vars
via django-environ — never commit them.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)

# Read .env if present (silent in prod where env is injected by the platform).
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# Chave de criptografia de campos (django-cryptography-5).
# Gerar com: Fernet.generate_key().decode()
# Em produção, vem de secret manager separado do backup do banco (ADR 0006).
CRYPTOGRAPHY_KEY = env("FIELD_ENCRYPTION_KEY").encode()


# IA (Anthropic) — ver ADR 0008.
# ANTHROPIC_API_KEY ausente → views de IA mostram erro amigável.
# ANTHROPIC_ZDR_CONFIRMED=false → cliente recusa chamadas (cinto de segurança).
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
ANTHROPIC_ZDR_CONFIRMED = env.bool("ANTHROPIC_ZDR_CONFIRMED", default=False)
ANTHROPIC_DEFAULT_MODEL = env("ANTHROPIC_DEFAULT_MODEL", default="claude-sonnet-4-6")


# Applications
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.bonds",
    "apps.journal",
    "apps.ai",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]


ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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


# Database
DATABASES = {
    "default": env.db("DATABASE_URL"),
}


# Auth
AUTH_USER_MODEL = "accounts.User"
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Senha não é caminho de auth no MoodTrack (CLAUDE.md regra 12).
# Mantemos validators do Django só para qualquer caso de borda em que um hash
# seja gerado por allauth/admin; o fluxo real é OAuth.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True


# Static / media
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Login redirects (Django built-in auth)
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "bonds:home"
LOGOUT_REDIRECT_URL = "login"


# DRF — defaults conservadores; ajustar quando endpoints surgirem.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
