"""Production settings — placeholder. Endurecer antes de qualquer deploy real."""

from .base import *

DEBUG = False

# Headers de segurança básicos. Revisar antes de deploy:
# - SECURE_HSTS_SECONDS, SECURE_HSTS_INCLUDE_SUBDOMAINS quando o domínio for fixado
# - CSP via django-csp (entra com a camada web)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
