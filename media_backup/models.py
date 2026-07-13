from django.db import models


class MediaFile(models.Model):
    """ຫຼັກຖານຮູບພາບ/ວິດີໂອ ກ່ອນ-ຫຼັງການບໍລິການ (Scope 2.3 — Media Backup)"""

    class Stage(models.TextChoices):
        BEFORE = "before", "ກ່ອນບໍລິການ"
        AFTER = "after", "ຫຼັງບໍລິການ"

    class MediaType(models.TextChoices):
        IMAGE = "image", "ຮູບພາບ"
        VIDEO = "video", "ວິດີໂອ"

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
    file = models.FileField("ໄຟລ໌", upload_to="assets/%Y/%m/")
    note = models.CharField("ໝາຍເຫດ", max_length=200, blank=True)
    uploaded_at = models.DateTimeField("ວັນທີອັບໂຫຼດ", auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "ໄຟລ໌ຫຼັກຖານ"
        verbose_name_plural = "ໄຟລ໌ຫຼັກຖານ"

    def __str__(self):
        return f"{self.asset.ticket_number} [{self.get_stage_display()}] {self.get_media_type_display()}"
