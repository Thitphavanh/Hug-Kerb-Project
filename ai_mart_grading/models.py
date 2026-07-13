from django.db import models


class ChecklistItem(models.Model):
    """ຫົວຂໍ້ກວດເຊັກສະພາບເກີບ (Scope 2.4 — AI Checklist Assessment)"""

    class Category(models.TextChoices):
        UPPER = "upper", "ໜ້າເກີບ (Upper)"
        SOLE = "sole", "ພື້ນເກີບ (Sole)"
        INSOLE = "insole", "ພື້ນໃນ (Insole)"
        LACES = "laces", "ສາຍເກີບ"
        BOX = "box", "ກ່ອງ/ອຸປະກອນເສີມ"
        OTHER = "other", "ອື່ນໆ"

    name = models.CharField("ຫົວຂໍ້ກວດ", max_length=200)
    category = models.CharField(
        "ໝວດ", max_length=20, choices=Category.choices, default=Category.OTHER
    )
    max_score = models.PositiveIntegerField("ຄະແນນເຕັມ", default=10)
    display_order = models.PositiveIntegerField("ລຳດັບສະແດງ", default=0)
    is_active = models.BooleanField("ໃຊ້ງານຢູ່", default=True)

    class Meta:
        ordering = ["display_order", "id"]
        verbose_name = "ຫົວຂໍ້ Checklist"
        verbose_name_plural = "ຫົວຂໍ້ Checklist"

    def __str__(self):
        return f"[{self.get_category_display()}] {self.name}"


class Assessment(models.Model):
    """ຜົນການປະເມີນສະພາບເກີບໂດຍ AI"""

    class Status(models.TextChoices):
        PENDING = "pending", "ລໍຖ້າປະເມີນ"
        DONE = "done", "ປະເມີນແລ້ວ"
        FAILED = "failed", "ຜິດພາດ"

    class Grade(models.TextChoices):
        A = "A", "A — ດີຫຼາຍ"
        B = "B", "B — ດີ"
        C = "C", "C — ພໍໃຊ້"
        D = "D", "D — ຊຸດໂຊມ"
        F = "F", "F — ເສຍຫາຍໜັກ"

    asset = models.ForeignKey(
        "asset_intake.Asset",
        on_delete=models.CASCADE,
        related_name="assessments",
        verbose_name="ເຄື່ອງຮັບຝາກ",
    )
    status = models.CharField(
        "ສະຖານະ", max_length=20, choices=Status.choices, default=Status.PENDING
    )
    overall_grade = models.CharField(
        "ເກຣດລວມ", max_length=1, choices=Grade.choices, blank=True
    )
    total_score = models.DecimalField(
        "ຄະແນນລວມ", max_digits=6, decimal_places=2, null=True, blank=True
    )
    summary = models.TextField("ສະຫຼູບຈາກ AI", blank=True)
    ai_model = models.CharField("AI Model", max_length=100, blank=True)
    raw_response = models.JSONField("ຄຳຕອບດິບຈາກ AI", null=True, blank=True)
    created_at = models.DateTimeField("ວັນທີປະເມີນ", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ການປະເມີນສະພາບ"
        verbose_name_plural = "ການປະເມີນສະພາບ"

    def __str__(self):
        return f"{self.asset.ticket_number} — {self.overall_grade or self.get_status_display()}"


class AssessmentItem(models.Model):
    """ຄະແນນແຕ່ລະຫົວຂໍ້ໃນການປະເມີນ"""

    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="ການປະເມີນ",
    )
    checklist_item = models.ForeignKey(
        ChecklistItem,
        on_delete=models.PROTECT,
        related_name="results",
        verbose_name="ຫົວຂໍ້ກວດ",
    )
    score = models.DecimalField("ຄະແນນ", max_digits=5, decimal_places=2)
    note = models.CharField("ໝາຍເຫດ", max_length=300, blank=True)

    class Meta:
        verbose_name = "ຄະແນນຫົວຂໍ້ກວດ"
        verbose_name_plural = "ຄະແນນຫົວຂໍ້ກວດ"

    def __str__(self):
        return f"{self.checklist_item.name}: {self.score}"
