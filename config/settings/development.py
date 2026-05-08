"""Development settings — não usar em produção."""

from .base import *
from .base import env

DEBUG = True

ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Permitir SECRET_KEY default em dev para reduzir atrito; em prod é obrigatório vir do env.
SECRET_KEY = env("SECRET_KEY", default="django-insecure-dev-only-change-me")

INTERNAL_IPS = ["127.0.0.1"]
