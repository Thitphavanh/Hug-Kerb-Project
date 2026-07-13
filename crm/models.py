from django.db import models


class Customer(models.Model):
    """ລູກຄ້າຂອງຮ້ານ (Scope 2.2 — CRM)"""

    name = models.CharField("ຊື່", max_length=150)
    phone = models.CharField("ເບີໂທ", max_length=30, unique=True)
    email = models.EmailField("ອີເມວ", blank=True)
    line_id = models.CharField("LINE / WhatsApp", max_length=100, blank=True)
    telegram_chat_id = models.CharField(
        "Telegram Chat ID",
        max_length=32,
        blank=True,
        help_text="ລູກຄ້າກົດ Start ໃສ່ bot ຂອງຮ້ານກ່ອນ ຈຶ່ງຈະໄດ້ chat id ມາຕື່ມບ່ອນນີ້",
    )
    facebook = models.CharField("Facebook", max_length=150, blank=True)
    address = models.TextField("ທີ່ຢູ່", blank=True)
    note = models.TextField("ໝາຍເຫດ", blank=True)
    created_at = models.DateTimeField("ວັນທີສ້າງ", auto_now_add=True)
    updated_at = models.DateTimeField("ອັບເດດລ່າສຸດ", auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ລູກຄ້າ"
        verbose_name_plural = "ລູກຄ້າ"

    def __str__(self):
        return f"{self.name} ({self.phone})"
