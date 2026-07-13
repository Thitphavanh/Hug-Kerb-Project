import uuid

from django.db import models


def generate_card_number():
    return "HK-" + uuid.uuid4().hex[:8].upper()


class MemberCard(models.Model):
    """ບັດສະມາຊິກດິຈິຕອນ (Scope 2.2)"""

    class Tier(models.TextChoices):
        BASIC = "basic", "Basic"
        SILVER = "silver", "Silver"
        GOLD = "gold", "Gold"

    customer = models.OneToOneField(
        "crm.Customer",
        on_delete=models.CASCADE,
        related_name="member_card",
        verbose_name="ລູກຄ້າ",
    )
    card_number = models.CharField(
        "ເລກບັດ", max_length=20, unique=True, default=generate_card_number
    )
    tier = models.CharField(
        "ລະດັບ", max_length=10, choices=Tier.choices, default=Tier.BASIC
    )
    points_balance = models.IntegerField("ຄະແນນສະສົມ", default=0)
    is_active = models.BooleanField("ໃຊ້ງານຢູ່", default=True)
    issued_at = models.DateTimeField("ວັນທີອອກບັດ", auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]
        verbose_name = "ບັດສະມາຊິກ"
        verbose_name_plural = "ບັດສະມາຊິກ"

    def __str__(self):
        return f"{self.card_number} — {self.customer.name}"


class PointTransaction(models.Model):
    """ລາຍການເຄື່ອນໄຫວຄະແນນສະສົມ"""

    card = models.ForeignKey(
        MemberCard,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name="ບັດສະມາຊິກ",
    )
    points = models.IntegerField("ຄະແນນ (+ ໄດ້ຮັບ / - ໃຊ້)")
    reason = models.CharField("ເຫດຜົນ", max_length=200)
    order = models.ForeignKey(
        "pos.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="point_transactions",
        verbose_name="ອໍເດີທີ່ກ່ຽວຂ້ອງ",
    )
    created_at = models.DateTimeField("ວັນທີ", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ລາຍການຄະແນນ"
        verbose_name_plural = "ລາຍການຄະແນນ"

    def __str__(self):
        return f"{self.card.card_number}: {self.points:+d} ({self.reason})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            MemberCard.objects.filter(pk=self.card_id).update(
                points_balance=models.F("points_balance") + self.points
            )
