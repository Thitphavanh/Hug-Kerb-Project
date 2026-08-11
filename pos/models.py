import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


CURRENCY_CHOICES = [
    ("THB", "THB (ບາດ)"),
    ("LAK", "LAK (ກີບ)"),
    ("USD", "USD (ໂດລາ)"),
]


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

    name = models.CharField("ຊື່ບໍລິການ", max_length=150)
    category = models.CharField(
        "ໝວດບໍລິການ",
        max_length=20,
        choices=Category.choices,
        default=Category.PRIMARY,
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
        OPEN = "open", "ເປີດຢູ່"
        PAID = "paid", "ຊຳລະແລ້ວ"
        CANCELLED = "cancelled", "ຍົກເລີກ"

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


class Payment(models.Model):
    """ການຮັບຊຳລະເງິນ (ລາຍຮັບ)"""

    class Method(models.TextChoices):
        CASH = "cash", "ເງິນສົດ"
        TRANSFER = "transfer", "ໂອນເງິນ"
        QR = "qr", "ສະແກນ QR"

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name="payments", verbose_name="ອໍເດີ"
    )
    amount = models.DecimalField("ຈຳນວນເງິນ", max_digits=12, decimal_places=2)
    currency = models.CharField(
        "ສະກຸນເງິນ", max_length=3, choices=CURRENCY_CHOICES, default="THB"
    )
    method = models.CharField(
        "ຊ່ອງທາງ", max_length=20, choices=Method.choices, default=Method.CASH
    )
    paid_at = models.DateTimeField("ວັນທີຊຳລະ", auto_now_add=True)
    note = models.CharField("ໝາຍເຫດ", max_length=200, blank=True)

    class Meta:
        ordering = ["-paid_at"]
        verbose_name = "ການຊຳລະເງິນ"
        verbose_name_plural = "ການຊຳລະເງິນ"

    def __str__(self):
        return f"{self.order.order_number}: {self.amount} {self.currency}"


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
