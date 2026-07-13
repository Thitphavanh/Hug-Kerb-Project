from django.db import models

from pos.models import CURRENCY_CHOICES


class PriceValuation(models.Model):
    """ຜົນປະເມີນລາຄາຂາຍຕໍ່ໂດຍ AI (Scope 2.4 — Price Valuation)"""

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
        "ສະກຸນເງິນ", max_length=3, choices=CURRENCY_CHOICES, default="THB"
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
