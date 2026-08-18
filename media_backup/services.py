"""ການເກັບໄຟລ໌ຫຼັກຖານ (Scope 2.3)

ຈຸດດຽວທີ່ໄຟລ໌ອັບໂຫຼດຖືກຂຽນລົງ disk — ໜ້າຮັບເຄື່ອງ ແລະ ໜ້າລາຍລະອຽດເອີ້ນອັນນີ້ຮ່ວມກັນ
ຈຶ່ງໝັ້ນໃຈໄດ້ວ່າການກວດຂະໜາດ/ຊະນິດຖືກໃຊ້ທຸກທາງເຂົ້າ ບໍ່ມີທາງລັດ.
"""

import hashlib

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_lazy

from .backends import BackupError, get_backup_backend
from .models import BackupRun, MediaFile
from .validators import UploadRejected, classify_upload

CHUNK_SIZE = 1024 * 1024


def _checksum(uploaded):
    """sha256 ຂອງໄຟລ໌ທີ່ອັບໂຫຼດ — ອ່ານເປັນທ່ອນ ບໍ່ໂຫຼດວິດີໂອທັງກ້ອນເຂົ້າ RAM"""
    digest = hashlib.sha256()
    for chunk in uploaded.chunks(CHUNK_SIZE):
        digest.update(chunk)
    # ອ່ານຈົນສຸດໄຟລ໌ແລ້ວ — ຕ້ອງກັບໄປຈຸດເລີ່ມ ບໍ່ດັ່ງນັ້ນທີ່ບັນທຶກລົງ disk ຈະຫວ່າງ
    uploaded.seek(0)
    return digest.hexdigest()


def store_uploads(*, asset, files, stage=None, capture_angle="", uploaded_by=None):
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
                uploaded_by=uploaded_by,
                checksum=_checksum(uploaded),
                size_bytes=uploaded.size,
            )
        )

    return created, errors


def pending_backup_queryset():
    """ໄຟລ໌ທີ່ຍັງບໍ່ໄດ້ສຳຮອງ — ເກົ່າກ່ອນ ເພື່ອບໍ່ໃຫ້ໄຟລ໌ຄ້າງດົນຖືກຂ້າມຕະຫຼອດ"""
    return MediaFile.objects.filter(backed_up_at__isnull=True).order_by("uploaded_at")


def run_backup(*, limit=None, backend=None):
    """ສຳເນົາໄຟລ໌ຫຼັກຖານທີ່ຍັງບໍ່ໄດ້ສຳຮອງໄປປາຍທາງ ແລ້ວຄືນ BackupRun

    ແລ່ນຊ້ຳກໍປອດໄພ ແລະ ແລ່ນຕໍ່ຈາກທີ່ຄ້າງໄດ້: ໄຟລ໌ທີ່ສຳຮອງແລ້ວຖືກຂ້າມ
    ຈຶ່ງຕັ້ງເປັນ cron ລາຍວັນໄດ້ ໂດຍບໍ່ຕ້ອງກັງວົນເລື່ອງຮອບທັບກັນ.

    ໄຟລ໌ໃດໜຶ່ງຕົກ ບໍ່ຢຸດທັງຮອບ — ບັນທຶກໄວ້ໃນ detail ແລ້ວໄປຕໍ່ ເພາະໄຟລ໌ເສຍ
    ໜຶ່ງອັນບໍ່ຄວນກັນບໍ່ໃຫ້ຫຼັກຖານທີ່ເຫຼືອຖືກສຳຮອງ.
    """
    backend = backend or get_backup_backend()
    if backend is None:
        raise BackupError(
            "ຍັງບໍ່ໄດ້ຕັ້ງປາຍທາງສຳຮອງ — ຕັ້ງ MEDIA_BACKUP_BACKEND ໃນ .env"
        )

    run = BackupRun.objects.create(destination=backend.describe())
    pending = pending_backup_queryset()
    if limit:
        pending = pending[:limit]

    problems = []
    for media in pending:
        try:
            with media.file.open("rb") as source:
                ref = backend.store(key=media.file.name, fileobj=source)
        except (BackupError, FileNotFoundError, OSError, ValueError) as exc:
            run.files_failed += 1
            problems.append(f"{media.file.name}: {exc}")
            continue

        media.backup_ref = ref
        media.backed_up_at = timezone.now()
        media.save(update_fields=["backup_ref", "backed_up_at"])
        run.files_copied += 1
        run.bytes_copied += media.size_bytes

    if run.files_failed == 0:
        run.status = BackupRun.Status.SUCCESS
    elif run.files_copied > 0:
        run.status = BackupRun.Status.PARTIAL
    else:
        run.status = BackupRun.Status.FAILED

    run.detail = "\n".join(problems[:50])
    run.finished_at = timezone.now()
    run.save(
        update_fields=[
            "status",
            "files_copied",
            "files_failed",
            "bytes_copied",
            "detail",
            "finished_at",
        ]
    )
    return run


# ══════════ ມຸມຖ່າຍຮູບຕອນຮັບເຄື່ອງ (Scope 2.3) ══════════
# ລຳດັບນີ້ຄືລຳດັບທີ່ພະນັກງານຖ່າຍຈິງໜ້າຮ້ານ: ພາບລວມກ່ອນ → ລົງລາຍລະອຽດ
# ໃຊ້ຮ່ວມກັນທັງ template, view ແລະ ເທັສ — ມີບ່ອນດຽວ ຈຶ່ງບໍ່ຫຼົງກັນ
INTAKE_PHOTO_SLOTS = (
    (MediaFile.CaptureAngle.FRONT, gettext_lazy("Front")),
    (MediaFile.CaptureAngle.HEEL, gettext_lazy("Back")),
    (MediaFile.CaptureAngle.LEFT, gettext_lazy("Left side")),
    (MediaFile.CaptureAngle.RIGHT, gettext_lazy("Right side")),
    (MediaFile.CaptureAngle.UPPER, gettext_lazy("Upper / body")),
    (MediaFile.CaptureAngle.LACES, gettext_lazy("Laces")),
    (MediaFile.CaptureAngle.OUTSOLE, gettext_lazy("Outsole")),
    (MediaFile.CaptureAngle.INSOLE, gettext_lazy("Insole")),
    (MediaFile.CaptureAngle.OXIDATION, gettext_lazy("Sole yellowing")),
)


def intake_photo_slots():
    """ຊ່ອງຖ່າຍຮູບພ້ອມຄ່າທີ່ template ຕ້ອງໃຊ້"""
    return [{"angle": angle, "label": label} for angle, label in INTAKE_PHOTO_SLOTS]


def store_slot_uploads(*, asset, get_files, prefix, stage=None, uploaded_by=None):
    """ເກັບຮູບຈາກຊ່ອງທີ່ແຍກຕາມມຸມ ແລ້ວຄືນ (ຈຳນວນທີ່ເກັບໄດ້, ຂໍ້ຄວາມຜິດພາດ)

    get_files(field_name) → ລາຍການໄຟລ໌ (ສົ່ງ request.FILES.getlist ເຂົ້າມາ)
    ຊ່ອງແຕ່ລະມຸມຊື່ "<prefix>_<angle>" ສ່ວນຮູບເພີ່ມເຕີມທີ່ບໍ່ລະບຸມຸມໃຊ້ "<prefix>"
    """
    saved, errors = 0, []

    for angle, _label in INTAKE_PHOTO_SLOTS:
        files = get_files(f"{prefix}_{angle}")
        if not files:
            continue
        created, problems = store_uploads(
            asset=asset,
            files=files,
            stage=stage,
            capture_angle=angle,
            uploaded_by=uploaded_by,
        )
        saved += len(created)
        errors.extend(problems)

    # ຮູບເພີ່ມເຕີມທີ່ບໍ່ເຂົ້າມຸມໃດ — ເຊັ່ນ ຮອຍເສຍຫາຍສະເພາະຈຸດ
    extra = get_files(prefix)
    if extra:
        created, problems = store_uploads(
            asset=asset, files=extra, stage=stage, uploaded_by=uploaded_by
        )
        saved += len(created)
        errors.extend(problems)

    return saved, errors
