from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from pos.models import CURRENCY_CHOICES


class TransactionType(models.TextChoices):
    INCOME = "IN", "ລາຍຮັບ"
    EXPENSE = "OUT", "ລາຍຈ່າຍ"


class AccountCategory(models.Model):
    name = models.CharField("ຊື່ໝວດ", max_length=120)
    transaction_type = models.CharField(
        "ປະເພດ", max_length=3, choices=TransactionType.choices
    )
    color = models.CharField("ສີ", max_length=7, default="#22d3ee")
    is_active = models.BooleanField("ໃຊ້ງານ", default=True)
    sort_order = models.PositiveSmallIntegerField("ລຳດັບ", default=0)
    # ໝວດ "ຍ້າຍເງິນລະຫວ່າງກະເປົ໋າຂອງຮ້ານເອງ" ເຊັ່ນ ເອົາເງິນສົດເຂົ້າບັນຊີທະນາຄານ.
    # ເງິນບໍ່ໄດ້ເຂົ້າ ຫຼື ອອກຈາກຮ້ານ ຈຶ່ງຕ້ອງບໍ່ນັບເປັນລາຍຮັບ/ລາຍຈ່າຍໃນທຸກລາຍງານ
    # ແຕ່ຍັງຕ້ອງເຫັນໃນໃບແຈ້ງຍອດ ເພາະຍອດເງິນສົດຫຼຸດ ແລະ ຍອດທະນາຄານເພີ່ມແທ້.
    is_internal_transfer = models.BooleanField(
        "ເປັນການຍ້າຍເງິນພາຍໃນ",
        default=False,
        help_text="ໝວດນີ້ຈະບໍ່ຖືກນັບເປັນລາຍຮັບ ຫຼື ລາຍຈ່າຍ",
    )

    class Meta:
        ordering = ["transaction_type", "sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "transaction_type"], name="unique_account_category"
            )
        ]
        verbose_name = "ໝວດບັນຊີ"
        verbose_name_plural = "ໝວດບັນຊີ"

    def __str__(self):
        return f"{self.get_transaction_type_display()} — {self.name}"


class CashBook(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = "cash", "ເງິນສົດ"
        TRANSFER = "transfer", "ໂອນເງິນ"
        QR = "qr", "ສະແກນ QR"
        OTHER = "other", "ອື່ນໆ"

    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "ຢືນຢັນແລ້ວ"
        DRAFT = "draft", "ສະບັບຮ່າງ"
        VOID = "void", "ຍົກເລີກ"

    date = models.DateField("ວັນທີ", default=timezone.localdate, db_index=True)
    time = models.TimeField("ເວລາ", default=timezone.localtime)
    description = models.CharField("ລາຍການ", max_length=255)
    transaction_type = models.CharField(
        "ປະເພດ", max_length=3, choices=TransactionType.choices, db_index=True
    )
    category = models.ForeignKey(
        AccountCategory,
        verbose_name="ໝວດ",
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    currency = models.CharField(
        "ສະກຸນເງິນ", max_length=3, choices=CURRENCY_CHOICES, default="LAK"
    )
    amount = models.DecimalField(
        "ຈຳນວນເງິນ",
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    payment_method = models.CharField(
        "ຊ່ອງທາງ",
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    reference = models.CharField("ເລກອ້າງອີງ", max_length=80, blank=True)
    # ການຍ້າຍເງິນ 1 ຄັ້ງ = 2 ແຖວ (ອອກຈາກກຳປັ່ນ + ເຂົ້າບັນຊີ) ຜູກກັນດ້ວຍລະຫັດນີ້
    # ເພື່ອໃຫ້ລຶບພ້ອມກັນທັງຄູ່ໄດ້ — ລຶບເຄິ່ງດຽວຈະເຮັດໃຫ້ບັນຊີບໍ່ສົມດຸນ
    transfer_group = models.UUIDField(
        "ລະຫັດຄູ່ຍ້າຍເງິນ", null=True, blank=True, editable=False, db_index=True
    )
    note = models.TextField("ໝາຍເຫດ", blank=True)
    attachment = models.FileField(
        "ຫຼັກຖານ/ໃບບິນ", upload_to="accounting/receipts/%Y/%m/", blank=True
    )
    status = models.CharField(
        "ສະຖານະ", max_length=12, choices=Status.choices, default=Status.CONFIRMED
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="ບັນທຶກໂດຍ",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cashbook_entries_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="ແກ້ໄຂໂດຍ",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cashbook_entries_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-time", "-created_at"]
        indexes = [
            models.Index(fields=["date", "currency", "transaction_type"]),
            models.Index(fields=["status", "date"]),
        ]
        verbose_name = "ລາຍການບັນຊີ"
        verbose_name_plural = "ລາຍການບັນຊີ"

    def __str__(self):
        return f"{self.date} — {self.description} ({self.amount} {self.currency})"

    @property
    def is_internal_transfer(self):
        return bool(self.category_id and self.category.is_internal_transfer)

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.category_id and self.category.transaction_type != self.transaction_type:
            raise ValidationError({"category": _("Category does not match transaction type.")})


class Budget(models.Model):
    month = models.DateField("ເດືອນ", help_text="ໃຊ້ວັນທີ 1 ຂອງເດືອນ")
    category = models.ForeignKey(
        AccountCategory,
        verbose_name="ໝວດ",
        on_delete=models.CASCADE,
        related_name="budgets",
        limit_choices_to={"transaction_type": TransactionType.EXPENSE},
    )
    currency = models.CharField(
        "ສະກຸນເງິນ", max_length=3, choices=CURRENCY_CHOICES, default="LAK"
    )
    amount = models.DecimalField(
        "ງົບປະມານ",
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta:
        ordering = ["-month", "category__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["month", "category", "currency"], name="unique_monthly_budget"
            )
        ]
        verbose_name = "ງົບປະມານ"
        verbose_name_plural = "ງົບປະມານ"

    def save(self, *args, **kwargs):
        self.month = self.month.replace(day=1)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.month:%m/%Y} — {self.category.name}: {self.amount} {self.currency}"


class CashHandover(models.Model):
    date = models.DateField("ວັນທີ", default=timezone.localdate)
    currency = models.CharField(
        "ສະກຸນເງິນ", max_length=3, choices=CURRENCY_CHOICES, default="LAK"
    )
    opening_balance = models.DecimalField(
        "ເງິນທອນຕົ້ນມື້", max_digits=15, decimal_places=2, default=0
    )
    expected_amount = models.DecimalField(
        "ຍອດຕາມລະບົບ", max_digits=15, decimal_places=2, default=0
    )
    counted_amount = models.DecimalField(
        "ຍອດນັບໄດ້", max_digits=15, decimal_places=2
    )
    note = models.TextField("ໝາຍເຫດ", blank=True)
    handed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="ຜູ້ສົ່ງມອບ",
        on_delete=models.SET_NULL,
        null=True,
        related_name="cash_handovers_given",
    )
    received_by = models.CharField("ຜູ້ຮັບ", max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "currency"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "currency"], name="unique_daily_cash_handover"
            )
        ]
        verbose_name = "ການສົ່ງມອບເງິນ"
        verbose_name_plural = "ການສົ່ງມອບເງິນ"

    @property
    def difference(self):
        return self.counted_amount - self.expected_amount

    def __str__(self):
        return f"{self.date} — {self.currency}: {self.counted_amount}"
