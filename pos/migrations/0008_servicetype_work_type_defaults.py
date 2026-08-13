"""ຕັ້ງຄ່າ work_type ເລີ່ມຕົ້ນໃຫ້ບໍລິການທີ່ມີຢູ່ແລ້ວ

ອິງຕາມ category ເປັນຫຼັກ ແລ້ວອິງຊື່ບໍລິການເປັນຕົວຊ່ວຍ
(Sole Restoration / Color Touch-up ເປັນ add_on ແຕ່ແມ່ນວຽກສ້ອມແປງ)
ຮ້ານປ່ຽນເອງໄດ້ພາຍຫຼັງໃນໜ້າ Admin.
"""

from django.db import migrations

CATEGORY_TO_WORK_TYPE = {
    "primary": "wash",
    "add_on": "repair",
    "ai_assessment": "assess",
    "buyback": "assess",
}

# ຄຳໃນຊື່ບໍລິການທີ່ບົ່ງບອກວ່າແມ່ນວຽກສ້ອມແປງ/ບູລະນະ
REPAIR_HINTS = ("restor", "repair", "touch-up", "touch up", "sole", "paint", "ສ້ອມ", "ທາສີ")
WASH_HINTS = ("clean", "wash", "spa", "deodor", "ຊັກ")


def set_work_types(apps, schema_editor):
    ServiceType = apps.get_model("pos", "ServiceType")
    for service in ServiceType.objects.all():
        name = (service.name or "").lower()
        if any(hint in name for hint in REPAIR_HINTS):
            work_type = "repair"
        elif any(hint in name for hint in WASH_HINTS):
            work_type = "wash"
        else:
            work_type = CATEGORY_TO_WORK_TYPE.get(service.category, "other")
        service.work_type = work_type
        service.save(update_fields=["work_type"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0007_servicetype_work_type"),
    ]

    operations = [
        migrations.RunPython(set_work_types, noop),
    ]
