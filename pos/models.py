import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


CURRENCY_CHOICES = [
    ("THB", _("THB (Baht)")),
    ("LAK", _("LAK (Kip)")),
    ("USD", _("USD (Dollar)")),
]

ZERO = Decimal("0")

# ສະກຸນເງິນຫຼັກຂອງບັນຊີ — ຍອດບິນ ແລະ ຍອດຄ້າງ ຄິດເປັນສະກຸນນີ້ສະເໝີ.
# ຮັບເງິນສະກຸນອື່ນໄດ້ ແຕ່ຕ້ອງມີອັດຕາແລກປ່ຽນ (fx_rate) ລັອກໄວ້ຕອນຈ່າຍ.
BASE_CURRENCY = getattr(settings, "POS_BASE_CURRENCY", "LAK")


def generate_order_number():
    # ຕໍ່ທ້າຍດ້ວຍເລກສຸ່ມ 3 ໂຕ — ກັນເລກຊ້ຳ ເມື່ອເປີດບິນຫຼາຍບິນໃນວິນາທີດຽວກັນ
    suffix = f"{secrets.randbelow(1000):03d}"
    return timezone.localtime().strftime("ORD%y%m%d%H%M%S") + suffix


class ServiceType(models.Model):
    """ປະເພດບໍລິການຂອງຮ້ານ ເຊັ່ນ ຊັກເກີບ, ທາສີຄືນ, ສ້ອມແປງ"""

    class Category(models.TextChoices):
        AI_ASSESSMENT = "ai_assessment", "AI assessment"
        PRIMARY = "primary", "Primary service"
        ADD_ON = "add_on", "Add-on service"
        # ບໍລິການຮັບຊື້-ຂາຍເກີບມືສອງ — AI ຊ່ວຍປະເມີນສະພາບ + ລາຄາຮັບຊື້
        BUYBACK = "buyback", "Second-hand buy-back"

    class WorkType(models.TextChoices):
        """ປະເພດວຽກໜ້າຮ້ານ — ໃຊ້ແຍກແຖວ (swimlane) ໃນກະດານຕິດຕາມການເຮັດວຽກ

        ຕ່າງຈາກ Category ທີ່ໃຊ້ຄິດລາຄາ: ອັນນີ້ບອກວ່າ "ໃຜເປັນຄົນເຮັດ"
        ເຊັ່ນ Sole Restoration ເປັນ add_on (ລາຄາ) ແຕ່ເປັນວຽກສ້ອມແປງ (ວຽກ)
        """

        WASH = "wash", _("Washing & cleaning")
        REPAIR = "repair", _("Repair & restoration")
        ASSESS = "assess", _("Condition assessment")
        OTHER = "other", _("Other work")

    name = models.CharField("ຊື່ບໍລິການ", max_length=150)
    category = models.CharField(
        "ໝວດບໍລິການ",
        max_length=20,
        choices=Category.choices,
        default=Category.PRIMARY,
    )
    work_type = models.CharField(
        "ປະເພດວຽກ",
        max_length=20,
        choices=WorkType.choices,
        default=WorkType.WASH,
        help_text="ໃຊ້ແຍກແຖວວຽກໃນກະດານຕິດຕາມການເຮັດວຽກ",
    )
    price = models.DecimalField("ລາຄາ", max_digits=12, decimal_places=2)
    is_active = models.BooleanField("ເປີດໃຫ້ບໍລິການ", default=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "ປະເພດບໍລິການ"
        verbose_name_plural = "ປະເພດບໍລິການ"

    def __str__(self):
        return f"{self.name} ({self.price})"


class Order(models.Model):
    """ອໍເດີ/ໃບບິນ (Scope 2.1 — POS)"""

    class Status(models.TextChoices):
        OPEN = "open", _("Open bill")
        PARTIALLY_PAID = "partially_paid", _("Partially paid")
        PAID = "paid", _("Paid in full")
        REFUNDED = "refunded", _("Refunded")
        CANCELLED = "cancelled", _("Cancelled")

    # ສະຖານະທີ່ຍັງເປີດຢູ່ໜ້າຮ້ານ — ໃຊ້ໃນໜ້າ "ບິນຄ້າງ"
    OPEN_STATUSES = ("open", "partially_paid")

    order_number = models.CharField(
        "ເລກອໍເດີ", max_length=20, unique=True, default=generate_order_number
    )
    customer = models.ForeignKey(
        "crm.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
        verbose_name="ລູກຄ້າ",
    )
    status = models.CharField(
        "ສະຖານະ", max_length=20, choices=Status.choices, default=Status.OPEN
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_orders",
        verbose_name="ພະນັກງານເປີດບິນ",
    )
    discount = models.DecimalField(
        "ສ່ວນຫຼຸດ", max_digits=12, decimal_places=2, default=0
    )
    vat_rate = models.IntegerField(
        "ອັດຕາ VAT (%)", default=10
    )
    note = models.TextField("ໝາຍເຫດ", blank=True)
    total_snapshot = models.DecimalField(
        "ຍອດລວມທີ່ລັອກໄວ້",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="ລັອກອັດຕະໂນມັດຕອນຊຳລະຄົບ — ແກ້ລາຄາພາຍຫຼັງຈະບໍ່ກະທົບໃບບິນເກົ່າ",
    )
    settled_at = models.DateTimeField("ວັນທີຊຳລະຄົບ", null=True, blank=True)
    created_at = models.DateTimeField("ວັນທີສ້າງ", auto_now_add=True)
    updated_at = models.DateTimeField("ອັບເດດລ່າສຸດ", auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ອໍເດີ"
        verbose_name_plural = "ອໍເດີ"

    def __str__(self):
        return self.order_number

    @property
    def subtotal(self):
        return sum((item.subtotal for item in self.items.all()), start=0)

    @property
    def vat_amount(self):
        return int((self.subtotal - self.discount) * self.vat_rate / 100)

    @property
    def total(self):
        return self.subtotal - self.discount + self.vat_amount

    # ------------------------------------------------------------------
    # ຍອດເງິນ — ຄິດຈາກ ledger ຂອງ Payment ສະເໝີ ບໍ່ແມ່ນຈາກ status
    # ------------------------------------------------------------------

    @property
    def effective_total(self):
        """ຍອດທີ່ຕ້ອງເກັບຈິງ — ໃຊ້ຍອດທີ່ລັອກໄວ້ຖ້າຊຳລະຄົບແລ້ວ"""
        if self.total_snapshot is not None:
            return self.total_snapshot
        return Decimal(self.total)

    @property
    def live_payments(self):
        """ແຖວການຊຳລະທີ່ຍັງມີຜົນ (ບໍ່ນັບແຖວທີ່ຖືກຍົກເລີກ)

        ວົນໃນ Python ບໍ່ແມ່ນ .filter() ເພື່ອໃຫ້ prefetch_related ໃຊ້ໄດ້
        """
        return [p for p in self.payments.all() if p.voided_at is None]

    @property
    def amount_paid(self):
        """ຮັບແລ້ວທັງໝົດ (ຫັກຄືນເງິນອອກແລ້ວ) ເປັນສະກຸນຫຼັກ"""
        return sum((p.signed_base_amount for p in self.live_payments), start=ZERO)

    @property
    def balance_due(self):
        return self.effective_total - self.amount_paid

    @property
    def is_settled(self):
        return self.balance_due <= ZERO

    def sync_status(self, commit=True):
        """ຄິດສະຖານະໃໝ່ຈາກ ledger — ຢ່າຕັ້ງ status ດ້ວຍມືອີກ

        ບິນທີ່ຍົກເລີກແລ້ວເປັນຈຸດຈົບ ຈະບໍ່ຖືກປ່ຽນອັດຕະໂນມັດ
        """
        if self.status == self.Status.CANCELLED:
            return self.status

        live = self.live_payments
        paid = sum((p.signed_base_amount for p in live), start=ZERO)
        has_refund = any(p.kind == Payment.Kind.REFUND for p in live)
        total = self.effective_total

        if paid <= ZERO:
            new_status = self.Status.REFUNDED if has_refund else self.Status.OPEN
        elif paid < total:
            new_status = self.Status.PARTIALLY_PAID
        else:
            new_status = self.Status.PAID

        changed = []
        if new_status != self.status:
            self.status = new_status
            changed.append("status")

        # ລັອກຍອດຕອນຂ້າມເສັ້ນເປັນ "ຊຳລະຄົບ" ຄັ້ງທຳອິດເທົ່ານັ້ນ
        if new_status == self.Status.PAID and self.total_snapshot is None:
            self.total_snapshot = Decimal(self.total)
            self.settled_at = timezone.now()
            changed += ["total_snapshot", "settled_at"]

        if commit and changed:
            self.save(update_fields=changed + ["updated_at"])
        return new_status

    def assets(self):
        """ເກີບທຸກຄູ່ໃນບິນນີ້ (ບໍ່ຊ້ຳ) — ໃຊ້ໃນໜ້າສົ່ງມອບເຄື່ອງ"""
        seen = {}
        for item in self.items.all():
            if item.asset_id and item.asset_id not in seen:
                seen[item.asset_id] = item.asset
        return list(seen.values())


class OrderItem(models.Model):
    """ລາຍການໃນອໍເດີ"""

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items", verbose_name="ອໍເດີ"
    )
    service_type = models.ForeignKey(
        ServiceType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items",
        verbose_name="ບໍລິການ",
    )
    asset = models.ForeignKey(
        "asset_intake.Asset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items",
        verbose_name="ເຄື່ອງຮັບຝາກ",
    )
    description = models.CharField("ລາຍລະອຽດ", max_length=200, blank=True)
    quantity = models.PositiveIntegerField("ຈຳນວນ", default=1)
    unit_price = models.DecimalField("ລາຄາຕໍ່ໜ່ວຍ", max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "ລາຍການອໍເດີ"
        verbose_name_plural = "ລາຍການອໍເດີ"

    def __str__(self):
        return f"{self.order.order_number}: {self.description or self.service_type}"

    @property
    def subtotal(self):
        return self.quantity * self.unit_price


class PaymentQuerySet(models.QuerySet):
    def live(self):
        """ສະເພາະແຖວທີ່ຍັງມີຜົນ — ຕັດແຖວທີ່ຖືກຍົກເລີກ (void) ອອກ"""
        return self.filter(voided_at__isnull=True)


class Payment(models.Model):
    """ການຮັບຊຳລະເງິນ (ລາຍຮັບ) — ເປັນ ledger ທີ່ເພີ່ມຢ່າງດຽວ

    ບໍ່ແກ້ ບໍ່ລຶບ: ຮັບຜິດ → ບັນທຶກ void ຫຼື ອອກແຖວຄືນເງິນ (refund) ໃໝ່
    """

    class Method(models.TextChoices):
        CASH = "cash", _("Cash")
        TRANSFER = "transfer", _("Bank transfer")
        QR = "qr", _("QR payment")

    class Kind(models.TextChoices):
        PAYMENT = "payment", _("Payment in")
        REFUND = "refund", _("Refund")

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name="payments", verbose_name="ອໍເດີ"
    )
    kind = models.CharField(
        "ປະເພດ", max_length=10, choices=Kind.choices, default=Kind.PAYMENT
    )
    amount = models.DecimalField("ຈຳນວນເງິນ", max_digits=12, decimal_places=2)
    currency = models.CharField(
        "ສະກຸນເງິນ", max_length=3, choices=CURRENCY_CHOICES, default="THB"
    )
    method = models.CharField(
        "ຊ່ອງທາງ", max_length=20, choices=Method.choices, default=Method.CASH
    )
    tendered_amount = models.DecimalField(
        "ເງິນທີ່ຮັບມາ",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="ຈຳນວນທີ່ລູກຄ້າຍື່ນມາຈິງ (ໃຊ້ກັບເງິນສົດ)",
    )
    change_amount = models.DecimalField(
        "ເງິນທອນ", max_digits=12, decimal_places=2, default=0
    )
    fx_rate = models.DecimalField(
        "ອັດຕາແລກປ່ຽນ",
        max_digits=18,
        decimal_places=6,
        default=1,
        help_text=f"ລັອກໄວ້ຕອນຈ່າຍ — ຄູນເປັນສະກຸນຫຼັກ ({BASE_CURRENCY})",
    )
    base_amount = models.DecimalField(
        "ຈຳນວນເງິນ (ສະກຸນຫຼັກ)", max_digits=14, decimal_places=2, default=0
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="received_payments",
        verbose_name="ພະນັກງານຮັບເງິນ",
    )
    idempotency_key = models.UUIDField(
        "ລະຫັດກັນບັນທຶກຊ້ຳ",
        null=True,
        blank=True,
        unique=True,
        help_text="ສ້າງຈາກຝັ່ງໜ້າຈໍ 1 ລະຫັດຕໍ່ 1 ການຈ່າຍ — ກົດຊ້ຳຈະບໍ່ບັນທຶກສອງແຖວ",
    )
    voided_at = models.DateTimeField("ຍົກເລີກເມື່ອ", null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="voided_payments",
        verbose_name="ຜູ້ຍົກເລີກ",
    )
    void_reason = models.CharField("ເຫດຜົນການຍົກເລີກ", max_length=200, blank=True)
    paid_at = models.DateTimeField("ວັນທີຊຳລະ", auto_now_add=True)
    note = models.CharField("ໝາຍເຫດ", max_length=200, blank=True)

    objects = PaymentQuerySet.as_manager()

    class Meta:
        ordering = ["-paid_at"]
        verbose_name = "ການຊຳລະເງິນ"
        verbose_name_plural = "ການຊຳລະເງິນ"

    def __str__(self):
        return f"{self.order.order_number}: {self.amount} {self.currency}"

    @property
    def is_voided(self):
        return self.voided_at is not None

    @property
    def signed_base_amount(self):
        """ຄ່າທີ່ເອົາໄປບວກເຂົ້າຍອດຮັບແລ້ວ — ຄືນເງິນເປັນຄ່າລົບ, void ເປັນສູນ"""
        if self.voided_at is not None:
            return ZERO
        base = self.base_amount or ZERO
        return -base if self.kind == self.Kind.REFUND else base

    def save(self, *args, **kwargs):
        # base_amount ຄິດຈາກ amount × fx_rate ຖ້າຜູ້ເອີ້ນບໍ່ໄດ້ກຳນົດມາເອງ
        if not self.base_amount:
            # ຄ່າອາດມາເປັນ int/str ຈາກຜູ້ເອີ້ນພາຍນອກ — ບັງຄັບເປັນ Decimal ກ່ອນຄູນ
            rate = Decimal(str(self.fx_rate)) if self.fx_rate is not None else Decimal("1")
            amount = Decimal(str(self.amount)) if self.amount is not None else ZERO
            self.base_amount = (amount * rate).quantize(Decimal("0.01"))
            update_fields = kwargs.get("update_fields")
            if update_fields is not None and "base_amount" not in update_fields:
                kwargs["update_fields"] = list(update_fields) + ["base_amount"]
        super().save(*args, **kwargs)


class Expense(models.Model):
    """ລາຍຈ່າຍຂອງຮ້ານ (Scope 2.1 — ບັນທຶກລາຍຮັບ-ລາຍຈ່າຍ)"""

    class Category(models.TextChoices):
        SUPPLIES = "supplies", "ອຸປະກອນ/ນ້ຳຢາ"
        RENT = "rent", "ຄ່າເຊົ່າ"
        UTILITY = "utility", "ຄ່ານ້ຳ/ໄຟ/ເນັດ"
        SALARY = "salary", "ເງິນເດືອນ"
        MARKETING = "marketing", "ການຕະຫຼາດ"
        OTHER = "other", "ອື່ນໆ"

    date = models.DateField("ວັນທີ", default=timezone.localdate)
    category = models.CharField(
        "ໝວດ", max_length=20, choices=Category.choices, default=Category.OTHER
    )
    description = models.CharField("ລາຍລະອຽດ", max_length=200)
    amount = models.DecimalField("ຈຳນວນເງິນ", max_digits=12, decimal_places=2)
    currency = models.CharField(
        "ສະກຸນເງິນ", max_length=3, choices=CURRENCY_CHOICES, default="THB"
    )
    created_at = models.DateTimeField("ບັນທຶກເມື່ອ", auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "ລາຍຈ່າຍ"
        verbose_name_plural = "ລາຍຈ່າຍ"

    def __str__(self):
        return f"{self.date} {self.get_category_display()}: {self.amount} {self.currency}"
