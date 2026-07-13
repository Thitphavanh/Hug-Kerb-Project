"""
Development settings for core project.
ການຕັ້ງຄ່າສຳລັບການພັດທະນາ (Development)

ການໃຊ້ງານ:
export DJANGO_SETTINGS_MODULE=core.settings.dev
python manage.py runserver
"""

import os

from .base import *

# SECURITY WARNING: keep the secret key used in production secret!
# ອ່ານຈາກ .env — ຖ້າບໍ່ມີ ໃຊ້ key ສຳຮອງສຳລັບ dev ເທົ່ານັ້ນ
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "1kuj44u*_(ocy*x)gnvs=yqm)47pd-8w2vk+#^snu9gl1%x5ji",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*", "localhost", "127.0.0.1"]

# ເຊື່ອ X-Forwarded-Proto ຈາກ ngrok — ໃຫ້ build_absolute_uri ອອກເປັນ https
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ອະນຸຍາດ POST form ຜ່ານ ngrok (URL ຂອງ ngrok free ປ່ຽນທຸກຄັ້ງ ຈຶ່ງໃຊ້ wildcard)
CSRF_TRUSTED_ORIGINS = [
    "https://*.ngrok-free.app",
    "https://*.ngrok.app",
    "https://*.ngrok.io",
]

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Show detailed error pages
DEBUG_PROPAGATE_EXCEPTIONS = True

# ໃຫ້ runserver ຮີສະຕາດເອງເມື່ອແກ້ໄຟລ໌ .env (ເຊັ່ນ ປ່ຽນ SITE_BASE_URL ເປັນ URL ngrok ໃໝ່)
from django.utils.autoreload import autoreload_started  # noqa: E402


def _watch_env_file(sender, **kwargs):
    sender.extra_files.add(BASE_DIR / ".env")


autoreload_started.connect(_watch_env_file)
