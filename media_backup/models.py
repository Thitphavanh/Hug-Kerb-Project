from django.conf import settings
from django.db import models


class MediaFile(models.Model):
    """ຫຼັກຖານຮູບພາບ/ວິດີໂອ ກ່ອນ-ຫຼັງການບໍລິການ (Scope 2.3 — Media Backup)"""

    class Stage(models.TextChoices):
        BEFORE = "before", "ກ່ອນບໍລິການ"
        AFTER = "after", "ຫຼັງບໍລິການ"

    class MediaType(models.TextChoices):
        IMAGE = "image", "ຮູບພາບ"
        VIDEO = "video", "ວິດີໂອ"

    class CaptureAngle(models.TextChoices):
        """ມຸມຖ່າຍຮູບຫຼັກຖານ — ຊື່ຄ່າເກົ່າຫ້າມປ່ຽນ ເພາະຮູບທີ່ເກັບໄວ້ແລ້ວອ້າງເຖິງມັນ"""

        FRONT = "front", "Front / toe box"
        HEEL = "heel", "Heel / rear"
        LEFT = "left", "Left side"
        RIGHT = "right", "Right side"
        SIDE = "side", "Side profile"
        UPPER = "upper", "Upper / body"
        LACES = "laces", "Laces"
        OUTSOLE = "outsole", "Outsole"
        INSOLE = "insole", "Insole"
        OXIDATION = "oxidation", "Sole yellowing (oxidation)"
        SIZE_LABEL = "size_label", "Size label / SKU"
        INNER = "inner", "Inner side / insole"
        BOX_ACCESSORIES = "box_accessories", "Box and accessories"
        DEFECT = "defect", "Defect close-up"

    asset = models.ForeignKey(
        "asset_intake.Asset",
        on_delete=models.CASCADE,
        related_name="media_files",
        verbose_name="ເຄື່ອງຮັບຝາກ",
    )
    stage = models.CharField(
        "ໄລຍະ", max_length=10, choices=Stage.choices, default=Stage.BEFORE
    )
    media_type = models.CharField(
        "ປະເພດໄຟລ໌", max_length=10, choices=MediaType.choices, default=MediaType.IMAGE
    )
    capture_angle = models.CharField(
        "ມຸມຮູບສຳລັບການປະເມີນ",
        max_length=30,
        choices=CaptureAngle.choices,
        blank=True,
    )
    file = models.FileField("ໄຟລ໌", upload_to="assets/%Y/%m/")
    note = models.CharField("ໝາຍເຫດ", max_length=200, blank=True)
    # ໃຜເປັນຄົນຖ່າຍ/ອັບໂຫຼດ — ຫຼັກຖານຈະໃຊ້ຢັນກັບລູກຄ້າໄດ້ ຕ້ອງສືບກັບໄປຫາຄົນໄດ້
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_media",
        verbose_name="ພະນັກງານຜູ້ອັບໂຫຼດ",
    )
    # sha256 ຕອນອັບໂຫຼດ — ໃຊ້ພິສູດວ່າສຳເນົາທີ່ສຳຮອງໄວ້ຍັງກົງກັບຕົ້ນສະບັບ
    checksum = models.CharField("Checksum (sha256)", max_length=64, blank=True)
    size_bytes = models.PositiveBigIntegerField("ຂະໜາດ (bytes)", default=0)
    backed_up_at = models.DateTimeField("ສຳຮອງເມື່ອ", null=True, blank=True)
    backup_ref = models.CharField("ບ່ອນເກັບສຳຮອງ", max_length=500, blank=True)
    uploaded_at = models.DateTimeField("ວັນທີອັບໂຫຼດ", auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            # ຄຳຖາມທີ່ run_backup() ຖາມທຸກຮອບ: "ໄຟລ໌ໃດຍັງບໍ່ໄດ້ສຳຮອງ"
            models.Index(fields=["backed_up_at"], name="media_backed_up_idx"),
        ]
        verbose_name = "ໄຟລ໌ຫຼັກຖານ"
        verbose_name_plural = "ໄຟລ໌ຫຼັກຖານ"

    def __str__(self):
        return f"{self.asset.ticket_number} [{self.get_stage_display()}] {self.get_media_type_display()}"

    @property
    def is_backed_up(self):
        return self.backed_up_at is not None


class BackupRun(models.Model):
    """ປະຫວັດການແລ່ນສຳຮອງ — ຫຼັກຖານວ່າແຜນ backup ເດີນຈິງ ບໍ່ແມ່ນຂຽນໄວ້ລອຍໆ"""

    class Status(models.TextChoices):
        RUNNING = "running", "ກຳລັງແລ່ນ"
        SUCCESS = "success", "ສຳເລັດ"
        PARTIAL = "partial", "ສຳເລັດບາງສ່ວນ"
        FAILED = "failed", "ຜິດພາດ"

    destination = models.CharField("ປາຍທາງ", max_length=300)
    status = models.CharField(
        "ສະຖານະ", max_length=20, choices=Status.choices, default=Status.RUNNING
    )
    files_copied = models.PositiveIntegerField("ໄຟລ໌ທີ່ສຳຮອງໄດ້", default=0)
    files_failed = models.PositiveIntegerField("ໄຟລ໌ທີ່ຕົກ", default=0)
    bytes_copied = models.PositiveBigIntegerField("ຂະໜາດລວມ (bytes)", default=0)
    detail = models.TextField("ລາຍລະອຽດ/ຂໍ້ຜິດພາດ", blank=True)
    started_at = models.DateTimeField("ເລີ່ມເມື່ອ", auto_now_add=True)
    finished_at = models.DateTimeField("ຈົບເມື່ອ", null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "ຮອບການສຳຮອງ"
        verbose_name_plural = "ຮອບການສຳຮອງ"

    def __str__(self):
        return f"{self.started_at:%Y-%m-%d %H:%M} → {self.get_status_display()} ({self.files_copied})"
