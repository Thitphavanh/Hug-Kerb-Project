import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def generate_ticket_number():
    """TK + ວັນເວລາ(ວິນາທີ) + ເລກສຸ່ມ 6 ໂຕ = 20 ໂຕ ພໍດີກັບ max_length

    ໃຊ້ 6 ໂຕ ບໍ່ແມ່ນ 3 — ເພາະ POS ສ້າງເກີບຫຼາຍຄູ່ໃນ loop ດຽວ (ວິນາທີດຽວກັນ)
    ຖ້າມີແຕ່ 1,000 ຄ່າຕໍ່ວິນາທີ ຮັບເກີບ ~37 ຄູ່ພ້ອມກັນ ມີໂອກາດຊ້ຳເຖິງ 50%
    ແລ້ວ unique constraint ຈະ error. 1,000,000 ຄ່າ ຫຼຸດຄວາມສ່ຽງລົງ 1000 ເທົ່າ.
    """
    suffix = f"{secrets.randbelow(1_000_000):06d}"
    return timezone.localtime().strftime("TK%y%m%d%H%M%S") + suffix


def generate_public_token():
    return secrets.token_urlsafe(12)


# ຜັງຊັ້ນວາງຈິງໜ້າຮ້ານ — ຕ້ອງກົງກັບປ້າຍທີ່ຕິດຢູ່ຝາ (ເບິ່ງ images/)
# slots = ຈຳນວນຊ່ອງທັງໝົດຂອງໂຊນ, per_row = ຈຳນວນຊ່ອງຕໍ່ໜຶ່ງຊັ້ນວາງ
ZONE_LAYOUT = {
    "A": {"label": "Zone A", "slots": 30, "per_row": 5},
    "B": {"label": "Zone B", "slots": 36, "per_row": 6},
    "V": {"label": "Zone VIP", "slots": 10, "per_row": 2},
}
DEFAULT_PER_ROW = 6


def zone_per_row(zone):
    return ZONE_LAYOUT.get(zone, {}).get("per_row", DEFAULT_PER_ROW)


def zone_label(zone):
    return ZONE_LAYOUT.get(zone, {}).get("label", f"Zone {zone}")


def build_zone_rows(slots, item_builder):
    """ຈັດ slots ເປັນ ໂຊນ > ຊັ້ນວາງ > ຊ່ອງ ຕາມຜັງຈິງໜ້າຮ້ານ

    ໃຊ້ຮ່ວມກັນລະຫວ່າງ Storage Map (asset_intake) ແລະ modal ເລືອກບ່ອນເກັບ (POS)
    ເພື່ອໃຫ້ສອງບ່ອນນີ້ສະແດງຜັງດຽວກັນສະເໝີ.
    """
    zones = {}
    counts = {}
    for slot in slots:
        zones.setdefault(slot.zone, {}).setdefault(slot.cabinet, []).append(
            item_builder(slot)
        )
        tally = counts.setdefault(slot.zone, {"total": 0, "free": 0})
        tally["total"] += 1
        if getattr(slot, "asset", None) is None:
            tally["free"] += 1

    return [
        {
            "name": zone,
            "label": zone_label(zone),
            "per_row": zone_per_row(zone),
            "total": counts[zone]["total"],
            "free": counts[zone]["free"],
            "occupied": counts[zone]["total"] - counts[zone]["free"],
            "rows": [
                {"number": row, "slots": items} for row, items in sorted(rows.items())
            ],
        }
        for zone, rows in sorted(zones.items())
    ]


class StorageSlot(models.Model):
    """ບ່ອນເກັບເກີບ — ແບ່ງເປັນ ໂຊນ > ຊັ້ນວາງ > ຊ່ອງ (ຄືຜັງຊັ້ນວາງຈິງໜ້າຮ້ານ)"""

    zone = models.CharField("ໂຊນ", max_length=10)
    cabinet = models.PositiveSmallIntegerField("ຕູ້", default=1)
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
        """ລະຫັດບ່ອນເກັບ ເຊັ່ນ B-05 — ກົງກັບປ້າຍທີ່ຕິດຢູ່ຊັ້ນວາງຈິງ"""
        return f"{self.zone}-{self.position:02d}"

    @property
    def zone_label(self):
        return zone_label(self.zone)

    def __str__(self):
        return self.code


class Asset(models.Model):
    """ເກີບ/ສິນຄ້າທີ່ຮັບຝາກເຂົ້າຮ້ານ (Scope 2.3 — Asset Intake)"""

    class Status(models.TextChoices):
        RECEIVED = "received", _("Received (intake)")
        CLEANING = "cleaning", _("Cleaning in progress")
        REPAIRING = "repairing", _("Repair in progress")
        READY = "ready", _("Ready for pickup")
        RETURNED = "returned", _("Handed over")

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
    # ຫຼັກຖານການສົ່ງມອບ (chain of custody) — ໃຜມາຮັບ ແລະ ພະນັກງານຄົນໃດເປັນຜູ້ມອບ
    returned_to = models.CharField("ຜູ້ມາຮັບເຄື່ອງ", max_length=120, blank=True)
    returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="handed_over_assets",
        verbose_name="ພະນັກງານຜູ້ມອບ",
    )
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

    def compute_status(self):
        """ຄິດໄລ່ສະຖານະຄູ່ຈາກສະຖານະຂອງແຕ່ລະບໍລິການ (ຫຼັກການ header/task rollup)

        ຄືນ None ຖ້າບໍ່ຄວນປ່ຽນສະຖານະອັດຕະໂນມັດ:
          - ສົ່ງມອບແລ້ວ → ຈຸດຈົບ, admin ຄຸມເອງ
          - ຍັງບໍ່ມີແຖວບໍລິການ → ໃຊ້ການຕັ້ງດ້ວຍມືຄືເກົ່າ
        """
        if self.status == self.Status.RETURNED:
            return None

        services = list(self.services.all())
        if not services:
            return None

        closed = [s for s in services if s.is_closed]
        if len(closed) == len(services):
            return self.Status.READY

        running = [s for s in services if s.status == AssetService.Status.IN_PROGRESS]
        if not running:
            return self.Status.RECEIVED

        # ມີວຽກສ້ອມແປງກຳລັງເຮັດ → ນັບເປັນ "ກຳລັງສ້ອມແປງ" (ເດັ່ນກວ່າ)
        from pos.models import ServiceType

        if any(s.work_type == ServiceType.WorkType.REPAIR for s in running):
            return self.Status.REPAIRING
        return self.Status.CLEANING

    # ລຳດັບຂັ້ນຕອນເຕັມຮູບແບບ — progress_stages() ຈະຕັດຂັ້ນທີ່ຄູ່ນີ້ບໍ່ຜ່ານອອກ
    STAGE_FLOW = (
        Status.RECEIVED,
        Status.CLEANING,
        Status.REPAIRING,
        Status.READY,
        Status.RETURNED,
    )

    def progress_stages(self):
        """ຂັ້ນຕອນທີ່ຄູ່ນີ້ຈະຜ່ານແທ້ໆ ຕາມວຽກທີ່ສັ່ງໄວ້

        ຄູ່ທີ່ມາຊັກຢ່າງດຽວບໍ່ຄວນເຫັນຂັ້ນ "ກຳລັງສ້ອມແປງ" ເພາະມັນຈະບໍ່ມີວັນໄປຮອດ —
        ໃຊ້ກົດດຽວກັບ compute_status() ຈຶ່ງບໍ່ມີຂັ້ນທີ່ສະຖານະຄິດໄລ່ໄປບໍ່ຮອດ
        ແລະ ກົງກັບກະດານຕິດຕາມວຽກທີ່ສະແດງສະເພາະແຖວທີ່ມີວຽກຈິງ.
        """
        from pos.models import ServiceType

        work_types = {s.work_type for s in self.services.all()}
        visible = {self.Status.RECEIVED, self.Status.READY, self.Status.RETURNED}

        if not work_types:
            # ຍັງບໍ່ມີແຖວວຽກ → ສະຖານະຄຸມດ້ວຍມື ຈຶ່ງຕ້ອງເຫັນທຸກຂັ້ນໄວ້ເລືອກ
            visible |= {self.Status.CLEANING, self.Status.REPAIRING}
        else:
            # compute_status() ຕີວຽກທີ່ບໍ່ແມ່ນສ້ອມແປງ (ຊັກ/ປະເມີນ/ອື່ນໆ) ເປັນ "ກຳລັງຊັກ"
            if work_types - {ServiceType.WorkType.REPAIR}:
                visible.add(self.Status.CLEANING)
            if ServiceType.WorkType.REPAIR in work_types:
                visible.add(self.Status.REPAIRING)

        # ສະຖານະປັດຈຸບັນຕ້ອງຢູ່ໃນລາຍການສະເໝີ ບໍ່ດັ່ງນັ້ນແຖບຄວາມຄືບໜ້າຈະຊີ້ຜິດຂັ້ນ
        visible.add(self.status)
        return [stage for stage in self.STAGE_FLOW if stage in visible]

    def rollup_status(self):
        """ອັບເດດ Asset.status ຕາມ compute_status() — ບັນທຶກສະເພາະເມື່ອປ່ຽນຈິງ"""
        new_status = self.compute_status()
        if new_status is None or new_status == self.status:
            return False
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])
        return True

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


class AssetService(models.Model):
    """ໜຶ່ງແຖວ = ໜຶ່ງບໍລິການທີ່ຕ້ອງເຮັດໃຫ້ເກີບຄູ່ນຶ່ງ

    ເປັນຫົວໃຈຂອງການແຍກ "ຊັກ" ກັບ "ສ້ອມແປງ" ອອກຈາກກັນ:
    ມາຊັກຢ່າງດຽວ = 1 ແຖວ, ມາສ້ອມຢ່າງດຽວ = 1 ແຖວ, ເຮັດທັງ 2 = 2 ແຖວ
    ທີ່ຍ້າຍສະຖານະເປັນອິດສະຫຼະຕໍ່ກັນ ແລະມອບໃຫ້ຊ່າງຄົນລະຄົນໄດ້.

    Asset.status ບໍ່ຕັ້ງເອງອີກຕໍ່ໄປ — ຄິດໄລ່ມາຈາກແຖວເຫຼົ່ານີ້ (ເບິ່ງ Asset.rollup_status)
    """

    class Status(models.TextChoices):
        PENDING = "pending", "ລໍຖ້າ (Pending)"
        IN_PROGRESS = "in_progress", "ກຳລັງເຮັດ (In progress)"
        DONE = "done", "ແລ້ວ (Done)"
        SKIPPED = "skipped", "ຂ້າມ (Skipped)"

    # ສະຖານະທີ່ຖືວ່າ "ຈົບແລ້ວ" — ບໍ່ຕ້ອງລໍອີກ
    CLOSED_STATUSES = (Status.DONE, Status.SKIPPED)

    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name="services",
        verbose_name="ເຄື່ອງຮັບຝາກ",
    )
    service_type = models.ForeignKey(
        "pos.ServiceType",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="asset_services",
        verbose_name="ບໍລິການ",
    )
    # ສຳເນົາຊື່ໄວ້ຕອນສ້າງ — ຖ້າລຶບ ServiceType ອອກ ກະດານຍັງສະແດງຊື່ວຽກໄດ້
    name = models.CharField("ຊື່ວຽກ", max_length=150, blank=True)
    work_type = models.CharField("ປະເພດວຽກ", max_length=20, blank=True)
    status = models.CharField(
        "ສະຖານະ", max_length=20, choices=Status.choices, default=Status.PENDING
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_services",
        verbose_name="ຊ່າງຮັບຜິດຊອບ",
    )
    started_at = models.DateTimeField("ເລີ່ມເມື່ອ", null=True, blank=True)
    finished_at = models.DateTimeField("ແລ້ວເມື່ອ", null=True, blank=True)
    created_at = models.DateTimeField("ສ້າງເມື່ອ", auto_now_add=True)

    class Meta:
        ordering = ["asset", "work_type", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "service_type"], name="unique_asset_service"
            )
        ]
        verbose_name = "ວຽກບໍລິການຕໍ່ຄູ່"
        verbose_name_plural = "ວຽກບໍລິການຕໍ່ຄູ່"

    def __str__(self):
        return f"{self.asset.ticket_number} — {self.label}"

    @property
    def label(self):
        return self.name or (self.service_type.name if self.service_type else "—")

    @property
    def is_closed(self):
        return self.status in self.CLOSED_STATUSES

    def save(self, *args, **kwargs):
        # ຕື່ມສຳເນົາຊື່/ປະເພດວຽກຈາກ ServiceType ອັດຕະໂນມັດ
        if self.service_type_id and not self.name:
            self.name = self.service_type.name
        if self.service_type_id and not self.work_type:
            self.work_type = self.service_type.work_type

        # ບັນທຶກເວລາເລີ່ມ/ແລ້ວ ໃຫ້ອັດຕະໂນມັດຕາມສະຖານະ
        now = timezone.now()
        if self.status == self.Status.IN_PROGRESS and self.started_at is None:
            self.started_at = now
        if self.status in self.CLOSED_STATUSES and self.finished_at is None:
            self.finished_at = now
        if self.status == self.Status.PENDING:
            self.started_at = None
            self.finished_at = None

        # update_fields ຖືກສົ່ງມາ → ຕ້ອງເພີ່ມ field ທີ່ເຮົາຫາກໍແກ້ ບໍ່ດັ່ງນັ້ນຈະບໍ່ຖືກບັນທຶກ
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {
                "name",
                "work_type",
                "started_at",
                "finished_at",
            }

        super().save(*args, **kwargs)
        self.asset.rollup_status()


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



class Brand(models.Model):
    """ຍີ່ຫໍ້ເກີບທີ່ຮ້ານຮັບ (Scope 2.3)

    ແຕ່ກ່ອນຍີ່ຫໍ້ຖືກຝັງແຂງໄວ້ໃນ template ຂອງໜ້າ POS ແລະ ພິມເອງຢູ່ໜ້າຮັບເຄື່ອງ
    ຜົນຄື "nike" ກັບ "Nike" ກາຍເປັນຄົນລະຍີ່ຫໍ້ ແລ້ວລາຍງານນັບແຍກກັນ.
    ເອົາມາເປັນຂໍ້ມູນທີ່ຮ້ານແກ້ເອງໄດ້ ຈຶ່ງເພີ່ມຍີ່ຫໍ້ໃໝ່ໂດຍບໍ່ຕ້ອງແກ້ໂຄ້ດ.
    """

    name = models.CharField("ຊື່ຍີ່ຫໍ້", max_length=100, unique=True)
    is_active = models.BooleanField("ເປີດໃຫ້ເລືອກ", default=True)
    sort_order = models.PositiveSmallIntegerField(
        "ລຳດັບ", default=0, help_text="ເລກນ້ອຍຂຶ້ນກ່ອນ — ຍີ່ຫໍ້ທີ່ຮັບປະຈຳໃຫ້ໃສ່ເລກນ້ອຍ"
    )
    created_at = models.DateTimeField("ວັນທີສ້າງ", auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "ຍີ່ຫໍ້ເກີບ"
        verbose_name_plural = "ຍີ່ຫໍ້ເກີບ"

    def __str__(self):
        return self.name


class ShoeModel(models.Model):
    """ລຸ້ນເກີບຂອງແຕ່ລະຍີ່ຫໍ້ — ໃຊ້ເປັນຕົວເລືອກແນະນຳຕອນຮັບເຄື່ອງ"""

    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name="shoe_models",
        verbose_name="ຍີ່ຫໍ້",
    )
    name = models.CharField("ຊື່ລຸ້ນ", max_length=150)
    is_active = models.BooleanField("ເປີດໃຫ້ເລືອກ", default=True)
    created_at = models.DateTimeField("ວັນທີສ້າງ", auto_now_add=True)

    class Meta:
        ordering = ["brand__sort_order", "brand__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["brand", "name"], name="unique_model_per_brand"
            )
        ]
        verbose_name = "ລຸ້ນເກີບ"
        verbose_name_plural = "ລຸ້ນເກີບ"

    def __str__(self):
        return f"{self.brand.name} {self.name}"
