"""
Production settings for core project.
ການຕັ້ງຄ່າສຳລັບການ Deploy ຂຶ້ນ Production

ການໃຊ້ງານ:
export DJANGO_SETTINGS_MODULE=core.settings.prod
"""

import os

from .base import *

# SECURITY WARNING: keep the secret key used in production secret!
# ໃຊ້ environment variable ສຳລັບ production
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "1kuj44u*_(ocy*x)gnvs=yqm)47pd-8w2vk+#^snu9gl1%x5ji",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# ອ່ານ domain ຈາກ .env ເຊັ່ນ: DJANGO_ALLOWED_HOSTS=hugkerb.com,www.hugkerb.com
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if h.strip()
]


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

# ຕົວຢ່າງການໃຊ້ PostgreSQL ສຳລັບ Production
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "hugkerb_db"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# ຫຼື ຖ້າຍັງໃຊ້ SQLite ສຳລັບ production ນ້ອຍໆ
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "db.sqlite3",
#     }
# }


# Static files ສຳລັບ production
STATIC_ROOT = BASE_DIR / "staticfiles"


# Security settings ສຳລັບ production
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
