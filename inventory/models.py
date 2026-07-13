from django.db import models


class Supply(models.Model):
    """ອຸປະກອນ/ວັດຖຸດິບພາຍໃນຮ້ານ (Scope 2.1 — Inventory)"""

    name = models.CharField("ຊື່ອຸປະກອນ", max_length=150)
    sku = models.CharField("ລະຫັດ (SKU)", max_length=50, unique=True)
    unit = models.CharField("ຫົວໜ່ວຍ", max_length=50, default="ອັນ")
    quantity_on_hand = models.IntegerField("ຈຳນວນຄົງເຫຼືອ", default=0)
    reorder_level = models.IntegerField("ຈຸດສັ່ງຊື້ຄືນ", default=0)
    cost_price = models.DecimalField(
        "ຕົ້ນທຶນຕໍ່ໜ່ວຍ", max_digits=12, decimal_places=2, default=0
    )
    is_active = models.BooleanField("ໃຊ້ງານຢູ່", default=True)
    created_at = models.DateTimeField("ວັນທີສ້າງ", auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "ອຸປະກອນສາງ"
        verbose_name_plural = "ອຸປະກອນສາງ"

    def __str__(self):
        return f"{self.name} ({self.quantity_on_hand} {self.unit})"

    @property
    def is_low_stock(self):
        return self.quantity_on_hand <= self.reorder_level


class StockMovement(models.Model):
    """ການເຄື່ອນໄຫວສະຕັອກ — ຮັບເຂົ້າ/ເບີກອອກ/ປັບຍອດ"""

    class MovementType(models.TextChoices):
        IN = "in", "ຮັບເຂົ້າ"
        OUT = "out", "ເບີກອອກ"
        ADJUST = "adjust", "ປັບຍອດ (+/-)"

    supply = models.ForeignKey(
        Supply,
        on_delete=models.PROTECT,
        related_name="movements",
        verbose_name="ອຸປະກອນ",
    )
    movement_type = models.CharField(
        "ປະເພດ", max_length=10, choices=MovementType.choices
    )
    quantity = models.IntegerField(
        "ຈຳນວນ", help_text="ຮັບເຂົ້າ/ເບີກອອກ ໃສ່ຈຳນວນບວກ; ປັບຍອດ ໃສ່ +/- ໄດ້"
    )
    note = models.CharField("ໝາຍເຫດ", max_length=200, blank=True)
    order = models.ForeignKey(
        "pos.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stock_movements",
        verbose_name="ອໍເດີທີ່ກ່ຽວຂ້ອງ",
    )
    created_at = models.DateTimeField("ວັນທີ", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ການເຄື່ອນໄຫວສະຕັອກ"
        verbose_name_plural = "ການເຄື່ອນໄຫວສະຕັອກ"

    def __str__(self):
        return f"{self.supply.name}: {self.get_movement_type_display()} {self.quantity}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            if self.movement_type == self.MovementType.IN:
                delta = abs(self.quantity)
            elif self.movement_type == self.MovementType.OUT:
                delta = -abs(self.quantity)
            else:
                delta = self.quantity
            Supply.objects.filter(pk=self.supply_id).update(
                quantity_on_hand=models.F("quantity_on_hand") + delta
            )
