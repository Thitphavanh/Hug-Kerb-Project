"""ກວດໄຟລ໌ຫຼັກຖານກ່ອນເກັບລົງ disk (Scope 2.3)

ເຫດຜົນ: ໄຟລ໌ຫຼັກຖານເກັບລົງ MEDIA_ROOT ຂອງເຄື່ອງໂດຍກົງ ແລະ ຮັບວິດີໂອນຳ.
ຖ້າບໍ່ມີເພດານ ຄລິບຍາວຄລິບດຽວກໍເຮັດໃຫ້ດິສເຕັມ ແລ້ວທັງຮ້ານຮັບເຄື່ອງບໍ່ໄດ້.

ກວດທັງນາມສະກຸນ ແລະ content-type: ນາມສະກຸນເປັນຕົວຕັດສິນຫຼັກ (ມັນຄືສິ່ງທີ່ຈະຖືກ
ຂຽນລົງ disk ຈິງ) ສ່ວນ content-type ໃຊ້ຢືນຢັນຊ້ຳ ເພາະປອມໄດ້ງ່າຍກວ່າ.
"""

import os

from django.conf import settings
from django.utils.translation import gettext as _

from .models import MediaFile

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".3gp"}
DOCUMENT_EXTENSIONS = {".pdf"}

BYTES_PER_MB = 1024 * 1024


class UploadRejected(Exception):
    """ໄຟລ໌ບໍ່ຜ່ານການກວດ — .message ເປັນຂໍ້ຄວາມທີ່ເອົາໄປສະແດງໃຫ້ຜູ້ໃຊ້ໄດ້ເລີຍ"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _limit_mb(media_type):
    if media_type == MediaFile.MediaType.VIDEO:
        return getattr(settings, "MAX_UPLOAD_VIDEO_MB", 60)
    return getattr(settings, "MAX_UPLOAD_IMAGE_MB", 12)


def classify_upload(uploaded_file):
    """ຄືນ media_type ຂອງໄຟລ໌ ຫຼື raise UploadRejected ພ້ອມເຫດຜົນທີ່ອ່ານເຂົ້າໃຈ"""
    name = uploaded_file.name or ""
    extension = os.path.splitext(name)[1].lower()

    if extension in IMAGE_EXTENSIONS:
        media_type = MediaFile.MediaType.IMAGE
    elif extension in VIDEO_EXTENSIONS:
        media_type = MediaFile.MediaType.VIDEO
    else:
        raise UploadRejected(
            _(
                "%(name)s: this file type is not supported. "
                "Use a photo (JPG, PNG, WEBP, HEIC) or a video (MP4, MOV, WEBM)."
            )
            % {"name": name}
        )

    # content-type ຕ້ອງບໍ່ຂັດກັບນາມສະກຸນ — ຮູບທີ່ຖືກປ່ຽນນາມສະກຸນມາຈະຕົກຢູ່ນີ້
    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    if content_type:
        expected_prefix = (
            "video/" if media_type == MediaFile.MediaType.VIDEO else "image/"
        )
        if not content_type.startswith(expected_prefix):
            raise UploadRejected(
                _("%(name)s: the file contents do not match its extension.")
                % {"name": name}
            )

    limit_mb = _limit_mb(media_type)
    _check_size(uploaded_file, limit_mb)

    return media_type


def _check_size(uploaded_file, limit_mb):
    if uploaded_file.size > limit_mb * BYTES_PER_MB:
        raise UploadRejected(
            _(
                "%(name)s is %(size).1f MB — larger than the %(limit)d MB limit. "
                "Shorten the video or take the photo at a lower resolution."
            )
            % {
                "name": uploaded_file.name,
                "size": uploaded_file.size / BYTES_PER_MB,
                "limit": limit_mb,
            }
        )


def validate_receipt(uploaded_file):
    """ກວດໄຟລ໌ໃບບິນ/ຫຼັກຖານທີ່ແນບໃນລາຍການບັນຊີ

    ຕ່າງຈາກຫຼັກຖານເກີບ: ຮັບ PDF ໄດ້ ແຕ່ບໍ່ຮັບວິດີໂອ ແລະ ໃຊ້ເພດານດຽວກັບຮູບ.
    """
    name = uploaded_file.name or ""
    extension = os.path.splitext(name)[1].lower()

    if extension not in IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS:
        raise UploadRejected(
            _("%(name)s: attach a photo (JPG, PNG, WEBP, HEIC) or a PDF.")
            % {"name": name}
        )

    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    if content_type:
        expected = "application/pdf" if extension == ".pdf" else "image/"
        if not content_type.startswith(expected):
            raise UploadRejected(
                _("%(name)s: the file contents do not match its extension.")
                % {"name": name}
            )

    _check_size(uploaded_file, getattr(settings, "MAX_UPLOAD_IMAGE_MB", 12))
    return uploaded_file
