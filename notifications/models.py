from django.db import models


class NotificationLog(models.Model):
    """ປະຫວັດການແຈ້ງເຕືອນລູກຄ້າ"""

    class Channel(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        WHATSAPP = "whatsapp", "WhatsApp"

    # ຫວ່າງໄດ້ — ການແຈ້ງເຕືອນບາງອັນເປັນຂອງລູກຄ້າ ບໍ່ແມ່ນຂອງເກີບຄູ່ໃດຄູ່ນຶ່ງ
    # (ເຊັ່ນ ບັດສະສົມ Stamp ທີ່ສົ່ງຫຼັງຮັບເງິນ)
    asset = models.ForeignKey(
        "asset_intake.Asset",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="ເຄື່ອງຮັບຝາກ",
    )
    customer = models.ForeignKey(
        "crm.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications",
        verbose_name="ລູກຄ້າ",
    )
    channel = models.CharField(
        "ຊ່ອງທາງ", max_length=20, choices=Channel.choices, default=Channel.TELEGRAM
    )
    recipient = models.CharField("ຜູ້ຮັບ", max_length=100)
    message = models.TextField("ຂໍ້ຄວາມ")
    is_sent = models.BooleanField("ສົ່ງສຳເລັດ", default=False)
    error = models.CharField("ຂໍ້ຜິດພາດ", max_length=300, blank=True)
    created_at = models.DateTimeField("ວັນທີ", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ການແຈ້ງເຕືອນ"
        verbose_name_plural = "ການແຈ້ງເຕືອນ"

    def __str__(self):
        status = "OK" if self.is_sent else "FAIL"
        subject = (
            self.asset.ticket_number
            if self.asset_id
            else (self.customer.name if self.customer_id else self.recipient)
        )
        return f"{subject} → {self.get_channel_display()} ({status})"
