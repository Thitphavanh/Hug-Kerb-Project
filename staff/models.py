from decimal import Decimal

from django.conf import settings
from django.db import models


class StaffProfile(models.Model):
    """ຂໍ້ມູນພະນັກງານ ແລະ ສິດທິການໃຊ້ງານ (ເຟສ 2 — Staff & Commission)"""

    class Role(models.TextChoices):
        MANAGER = "manager", "ຜູ້ຈັດການ (ເບິ່ງໄດ້ໝົດ)"
        FRONT_DESK = "front_desk", "ໜ້າຮ້ານ (ເປີດບິນ)"
        TECHNICIAN = "technician", "ຊ່າງຊັກເກີບ"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_profile",
        verbose_name="ບັນຊີຜູ້ໃຊ້",
    )
    role = models.CharField(
        "ໜ້າທີ່", max_length=20, choices=Role.choices, default=Role.TECHNICIAN
    )
    phone = models.CharField("ເບີໂທ", max_length=30, blank=True)
    commission_rate = models.DecimalField(
        "ອັດຕາຄອມມິດຊັນ (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        help_text="ເປີເຊັນຈາກຄ່າບໍລິການຂອງວຽກທີ່ຊ່າງຄົນນີ້ເຮັດສຳເລັດ",
    )
    is_active = models.BooleanField("ເຮັດວຽກຢູ່", default=True)
    created_at = models.DateTimeField("ວັນທີສ້າງ", auto_now_add=True)

    class Meta:
        ordering = ["user__username"]
        verbose_name = "ພະນັກງານ"
        verbose_name_plural = "ພະນັກງານ"

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} — {self.get_role_display()}"


def get_role(user):
    """ຄືນຄ່າໜ້າທີ່ຂອງ user — superuser ຖືເປັນຜູ້ຈັດການສະເໝີ"""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return StaffProfile.Role.MANAGER
    profile = getattr(user, "staff_profile", None)
    if profile and profile.is_active:
        return profile.role
    return None
