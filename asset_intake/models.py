import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


def generate_ticket_number():
    # ຕໍ່ທ້າຍດ້ວຍເລກສຸ່ມ 3 ໂຕ — ກັນເລກຊ້ຳ ເມື່ອຮັບເກີບຫຼາຍຄູ່ໃນວິນາທີດຽວກັນ
    suffix = f"{secrets.randbelow(1000):03d}"
    return timezone.localtime().strftime("TK%y%m%d%H%M%S") + suffix


def generate_public_token():
    return secrets.token_urlsafe(12)


class StorageSlot(models.Model):
    """ບ່ອນເກັບເກີບ — ແບ່ງເປັນ ໂຊນ > ຕູ້ > ຊ່ອງ (ຄືຜັງບ່ອນນັ່ງໂຮງໜັງ)"""

    zone = models.CharField("ໂຊນ", max_length=10)
    cabinet = models.PositiveSmallIntegerField("ຕູ້")
    position = models.PositiveSmallIntegerField("ຊ່ອງ")
    is_active = models.BooleanField("ເປີດໃຊ້ງານ", default=True)

    class Meta:
        ordering = ["zone", "cabinet", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["zone", "cabinet", "position"], name="unique_storage_slot"
            )
        ]
        verbose_name = "ບ່ອນເກັບເກີບ"
        verbose_name_plural = "ບ່ອນເກັບເກີບ"

    @property
    def code(self):
        """ລະຫັດບ່ອນເກັບ ເຊັ່ນ A1-05 (ໂຊນ A ຕູ້ 1 ຊ່ອງ 5)"""
        return f"{self.zone}{self.cabinet}-{self.position:02d}"

    def __str__(self):
        return self.code


class Asset(models.Model):
    """ເກີບ/ສິນຄ້າທີ່ຮັບຝາກເຂົ້າຮ້ານ (Scope 2.3 — Asset Intake)"""

    class Status(models.TextChoices):
        RECEIVED = "received", "ຮັບເຂົ້າ (Intake)"
        CLEANING = "cleaning", "ກຳລັງທຳຄວາມສະອາດ (Cleaning)"
        REPAIRING = "repairing", "ກຳລັງສ້ອມແປງ (Repairing)"
        READY = "ready", "ສຳເລັດ/ລໍຖ້າຮັບ (Ready for Pickup)"
        RETURNED = "returned", "ສົ່ງມອບແລ້ວ (Completed)"

    ticket_number = models.CharField(
        "ເລກໃບຮັບເຄື່ອງ", max_length=20, unique=True, default=generate_ticket_number
    )
    public_token = models.CharField(
        "ລະຫັດຕິດຕາມ (ສຳລັບ QR/Portal)",
        max_length=32,
        unique=True,
        default=generate_public_token,
        editable=False,
    )
    customer = models.ForeignKey(
        "crm.Customer",
        on_delete=models.PROTECT,
        related_name="assets",
        verbose_name="ລູກຄ້າ",
    )
    brand = models.CharField("ຍີ່ຫໍ້", max_length=100)
    model_name = models.CharField("ລຸ້ນ", max_length=150, blank=True)
    color = models.CharField("ສີ", max_length=100, blank=True)
    size = models.CharField("ເບີ", max_length=20, blank=True)
    condition_note = models.TextField("ສະພາບຕອນຮັບເຄື່ອງ", blank=True)
    status = models.CharField(
        "ສະຖານະ", max_length=20, choices=Status.choices, default=Status.RECEIVED
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_assets",
        verbose_name="ຊ່າງຮັບຜິດຊອບ",
    )
    storage_slot = models.OneToOneField(
        StorageSlot,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="asset",
        verbose_name="ບ່ອນເກັບ",
    )
    intake_date = models.DateTimeField("ວັນທີຮັບເຂົ້າ", auto_now_add=True)
    pickup_date = models.DateField("ວັນນັດຮັບເຄື່ອງ", null=True, blank=True)
    completed_at = models.DateTimeField("ວັນທີສົ່ງມອບ", null=True, blank=True)
    updated_at = models.DateTimeField("ອັບເດດລ່າສຸດ", auto_now=True)

    class Meta:
        ordering = ["-intake_date"]
        verbose_name = "ເຄື່ອງຮັບຝາກ"
        verbose_name_plural = "ເຄື່ອງຮັບຝາກ"

    def __str__(self):
        return f"{self.ticket_number} — {self.brand} {self.model_name}".strip()

    def get_portal_url(self):
        """URL ໜ້າຕິດຕາມສະຖານະຂອງລູກຄ້າ (public)"""
        return reverse("digital_member:track", args=[self.public_token])

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_status = None
        if not is_new:
            old_status = (
                Asset.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
        status_changed = old_status is not None and old_status != self.status

        # ບັນທຶກວັນທີສົ່ງມອບ ເມື່ອປ່ຽນສະຖານະເປັນ "ສົ່ງມອບແລ້ວ"
        if (
            status_changed
            and self.status == self.Status.RETURNED
            and self.completed_at is None
        ):
            self.completed_at = timezone.now()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"completed_at"}

        # ສົ່ງມອບແລ້ວ → ຄືນບ່ອນເກັບໃຫ້ຫວ່າງອັດຕະໂນມັດ (ທຸກເສັ້ນທາງ: detail, kanban, admin)
        if (
            status_changed
            and self.status == self.Status.RETURNED
            and self.storage_slot_id is not None
        ):
            self.storage_slot = None
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"storage_slot"}

        super().save(*args, **kwargs)

        # ແຈ້ງເຕືອນລູກຄ້າທຸກຄັ້ງທີ່ຂັ້ນຕອນປ່ຽນ ລວມທັງຕອນຮັບເຂົ້າໃໝ່
        # (notification ພັງ ບໍ່ກະທົບການບັນທຶກ — ຈັດການ error ໃນ service)
        if is_new or status_changed:
            from notifications.services import notify_status_change

            notify_status_change(self)


class AssetImage(models.Model):
    """ຮູບພາບກ່ອນ-ຫຼັງຊັກ (Scope 2.3 — Before/After Gallery)"""

    class ImageType(models.TextChoices):
        BEFORE = "before", "ກ່ອນຊັກ (Before)"
        AFTER = "after", "ຫຼັງຊັກ (After)"

    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="images", verbose_name="ເຄື່ອງຮັບຝາກ"
    )
    image = models.ImageField("ຮູບພາບ", upload_to="assets/%Y/%m/")
    image_type = models.CharField(
        "ປະເພດຮູບ", max_length=10, choices=ImageType.choices, default=ImageType.BEFORE
    )
    uploaded_at = models.DateTimeField("ອັບໂຫຼດເມື່ອ", auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "ຮູບພາບເກີບ"
        verbose_name_plural = "ຮູບພາບເກີບ"

    def __str__(self):
        return f"{self.asset.ticket_number} - {self.get_image_type_display()}"

