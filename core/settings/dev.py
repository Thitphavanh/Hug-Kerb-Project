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
