"""ການເກັບໄຟລ໌ຫຼັກຖານ (Scope 2.3)

ຈຸດດຽວທີ່ໄຟລ໌ອັບໂຫຼດຖືກຂຽນລົງ disk — ໜ້າຮັບເຄື່ອງ ແລະ ໜ້າລາຍລະອຽດເອີ້ນອັນນີ້ຮ່ວມກັນ
ຈຶ່ງໝັ້ນໃຈໄດ້ວ່າການກວດຂະໜາດ/ຊະນິດຖືກໃຊ້ທຸກທາງເຂົ້າ ບໍ່ມີທາງລັດ.
"""

from django.conf import settings
from django.utils.translation import gettext as _

from .models import MediaFile
from .validators import UploadRejected, classify_upload


def store_uploads(*, asset, files, stage=None, capture_angle=""):
    """ເກັບໄຟລ໌ທີ່ຜ່ານການກວດ ແລ້ວຄືນ (ລາຍການທີ່ເກັບໄດ້, ລາຍການຂໍ້ຄວາມຜິດພາດ)

    ໄຟລ໌ທີ່ຕົກການກວດຈະຖືກຂ້າມໄປ ແຕ່ໄຟລ໌ທີ່ດີຍັງຖືກເກັບຕາມປົກກະຕິ —
    ພະນັກງານເລືອກຮູບເທື່ອລະຫຼາຍໃບ ບໍ່ຄວນເສຍທັງຊຸດຍ້ອນໃບດຽວໃຫຍ່ເກີນ.
    """
    stage = stage or MediaFile.Stage.BEFORE
    created = []
    errors = []

    max_files = getattr(settings, "MAX_UPLOAD_FILES_PER_REQUEST", 20)
    if len(files) > max_files:
        errors.append(
            _("Only the first %(limit)d files were uploaded — select fewer at a time.")
            % {"limit": max_files}
        )
        files = files[:max_files]

    for uploaded in files:
        try:
            media_type = classify_upload(uploaded)
        except UploadRejected as rejection:
            errors.append(rejection.message)
            continue

        created.append(
            MediaFile.objects.create(
                asset=asset,
                file=uploaded,
                stage=stage,
                media_type=media_type,
                capture_angle=capture_angle,
            )
        )

    return created, errors
