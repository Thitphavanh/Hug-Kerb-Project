from django.db import models

from pos.models import CURRENCY_CHOICES


class PriceValuation(models.Model):
    """ຜົນປະເມີນລາຄາຂາຍຕໍ່ໂດຍ AI (Scope 2.4 — Price Valuation)

    ຕົວເລກທີ່ AI ຕອບກັບມາເກັບເປັນຖັນຈິງທຸກຄ່າ ບໍ່ແມ່ນຄົ້ນເອົາຈາກ raw_response —
    ໜ້າຈໍ, ລາຍງານ ແລະ admin ຕ້ອງກັ່ນຕອງ/ຈັດລຽງຕາມລາຄາຮັບຊື້ ແລະ ຄວາມໝັ້ນໃຈໄດ້,
    ເຊິ່ງເຮັດກັບ JSONField ບໍ່ໄດ້. raw_response ຍັງເກັບໄວ້ເປັນຫຼັກຖານດິບຄືເກົ່າ.
    """

    class DemandLevel(models.TextChoices):
        HIGH = "High Demand", "ຄວາມຕ້ອງການສູງ"
        NORMAL = "Normal Demand", "ຄວາມຕ້ອງການປົກກະຕິ"
        LOW = "Low Demand", "ຄວາມຕ້ອງການຕ່ຳ"

    asset = models.ForeignKey(
        "asset_intake.Asset",
        on_delete=models.CASCADE,
        related_name="valuations",
        verbose_name="ເຄື່ອງຮັບຝາກ",
    )
    assessment = models.ForeignKey(
        "ai_mart_grading.Assessment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="valuations",
        verbose_name="ການປະເມີນສະພາບ",
    )
    price_min = models.DecimalField("ລາຄາຕ່ຳສຸດ", max_digits=12, decimal_places=2)
    price_max = models.DecimalField("ລາຄາສູງສຸດ", max_digits=12, decimal_places=2)
    suggested_price = models.DecimalField(
        "ລາຄາແນະນຳ", max_digits=12, decimal_places=2
    )
    currency = models.CharField(
        "ສະກຸນເງິນ", max_length=3, choices=CURRENCY_CHOICES, default="LAK"
    )
    # ----- ການແຍກລາຄາ (ສະແດງໃນບັດ Buy-back ໜ້າລາຍລະອຽດ) -----
    base_price = models.DecimalField(
        "ລາຄາຕະຫຼາດພື້ນຖານ", max_digits=12, decimal_places=2, null=True, blank=True
    )
    condition_adjustment = models.DecimalField(
        "ປັບຕາມສະພາບ", max_digits=12, decimal_places=2, null=True, blank=True
    )
    rarity_premium = models.DecimalField(
        "ບວກຄວາມຫາຍາກ", max_digits=12, decimal_places=2, null=True, blank=True
    )
    refurbishment_cost = models.DecimalField(
        "ຄ່າຟື້ນຟູ", max_digits=12, decimal_places=2, null=True, blank=True
    )
    risk_reserve = models.DecimalField(
        "ສຳຮອງຄວາມສ່ຽງ", max_digits=12, decimal_places=2, null=True, blank=True
    )
    target_margin_percent = models.DecimalField(
        "ກຳໄລເປົ້າໝາຍ (%)", max_digits=5, decimal_places=2, null=True, blank=True
    )
    recommended_buy_price = models.DecimalField(
        "ລາຄາຮັບຊື້ທີ່ແນະນຳ",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="ລາຄາທີ່ຮ້ານຄວນສະເໜີຊື້ — ຕ່ຳກວ່າລາຄາຂາຍຕໍ່ສະເໝີ",
    )
    demand_level = models.CharField(
        "ລະດັບຄວາມຕ້ອງການ",
        max_length=20,
        choices=DemandLevel.choices,
        blank=True,
    )
    confidence_score = models.DecimalField(
        "ຄວາມໝັ້ນໃຈຂອງ AI (%)", max_digits=5, decimal_places=2, null=True, blank=True
    )
    reasoning = models.TextField("ເຫດຜົນຈາກ AI", blank=True)
    ai_model = models.CharField("AI Model", max_length=100, blank=True)
    raw_response = models.JSONField("ຄຳຕອບດິບຈາກ AI", null=True, blank=True)
    created_at = models.DateTimeField("ວັນທີປະເມີນ", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ການປະເມີນລາຄາ"
        verbose_name_plural = "ການປະເມີນລາຄາ"

    def __str__(self):
        return f"{self.asset.ticket_number}: {self.suggested_price} {self.currency}"


class PromoContent(models.Model):
    """ເນື້ອຫາໂປຣໂມດການຕະຫຼາດທີ່ AI ສ້າງ (Scope 2.4 — AI Promotional Marketing)"""

    class Platform(models.TextChoices):
        FACEBOOK = "facebook", "Facebook"
        TIKTOK = "tiktok", "TikTok"
        INSTAGRAM = "instagram", "Instagram"
        OTHER = "other", "ອື່ນໆ"

    asset = models.ForeignKey(
        "asset_intake.Asset",
        on_delete=models.CASCADE,
        related_name="promo_contents",
        verbose_name="ເຄື່ອງຮັບຝາກ",
    )
    platform = models.CharField(
        "ແພລດຟອມ", max_length=20, choices=Platform.choices, default=Platform.FACEBOOK
    )
    content = models.TextField("ເນື້ອຫາໂປຣໂມດ")
    ai_model = models.CharField("AI Model", max_length=100, blank=True)
    created_at = models.DateTimeField("ວັນທີສ້າງ", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ເນື້ອຫາໂປຣໂມດ"
        verbose_name_plural = "ເນື້ອຫາໂປຣໂມດ"

    def __str__(self):
        return f"{self.asset.ticket_number} → {self.get_platform_display()}"
