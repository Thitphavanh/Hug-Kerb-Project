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
    stamps_count = models.IntegerField("Stamp ສະສົມ", default=0)
    stamps_redeemed = models.IntegerField("Stamp ທີ່ແລກສ່ວນຫຼຸດແລ້ວ", default=0)
    is_active = models.BooleanField("ໃຊ້ງານຢູ່", default=True)
    issued_at = models.DateTimeField("ວັນທີອອກບັດ", auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]
        verbose_name = "ບັດສະມາຊິກ"
        verbose_name_plural = "ບັດສະມາຊິກ"

    def __str__(self):
        return f"{self.card_number} — {self.customer.name}"

    @property
    def rewards_earned(self):
        """ຈຳນວນສິດສ່ວນຫຼຸດທີ່ໄດ້ຮັບທັງໝົດ (10 stamps = 1 ສ່ວນຫຼຸດ)"""
        return self.stamps_count // 10

    @property
    def rewards_available(self):
        """ຈຳນວນສິດສ່ວນຫຼຸດທີ່ສາມາດນຳໃຊ້ໄດ້ໃນປະຈຸບັນ"""
        return max(0, (self.stamps_count // 10) - self.stamps_redeemed)

    @property
    def current_stamps(self):
        """ຈຳນວນ stamp ໃນຮອບປະຈຸບັນ (0 ຫາ 10)"""
        if self.stamps_count > 0 and self.stamps_count % 10 == 0 and self.rewards_available > 0:
            return 10
        return self.stamps_count % 10

    @property
    def stamps_progress_percent(self):
        return min(100, int((self.current_stamps / 10) * 100))

    @property
    def stamp_slots(self):
        """ລາຍການ 10 slots ສຳລັບ render UI stamp card"""
        cur = self.current_stamps
        return [
            {
                "number": i,
                "is_stamped": i <= cur,
                "is_reward_slot": i == 10,
            }
            for i in range(1, 11)
        ]



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


class StampTransaction(models.Model):
    """ລາຍການເຄື່ອນໄຫວ Stamp ສະສົມ"""

    class Action(models.TextChoices):
        ADD = "ADD", "ເພີ່ມ Stamp"
        REDEEM = "REDEEM", "ນຳໃຊ້ສ່ວນຫຼຸດ"
        RESET = "RESET", "ເລີ່ມໃໝ່"

    card = models.ForeignKey(
        MemberCard,
        on_delete=models.CASCADE,
        related_name="stamp_transactions",
        verbose_name="ບັດສະມາຊິກ",
    )
    action = models.CharField(
        "ການກະທຳ", max_length=10, choices=Action.choices, default=Action.ADD
    )
    count = models.IntegerField("ຈຳນວນ Stamp", default=1)
    note = models.CharField("ໝາຍເຫດ", max_length=200, blank=True)
    created_at = models.DateTimeField("ວັນທີ", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ລາຍການ Stamp"
        verbose_name_plural = "ລາຍການ Stamp"

    def __str__(self):
        return f"{self.card.card_number}: {self.get_action_display()} ({self.count})"

