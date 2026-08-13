"""ປັບເລກຊ່ອງໃຫ້ກົງກັບປ້າຍທີ່ຕິດຢູ່ຊັ້ນວາງຈິງໜ້າຮ້ານ

ເກົ່າ: ຊ່ອງນັບໃໝ່ທຸກຕູ້ → A1-05 ແລະ A2-05 (ສອງບ່ອນ ແຕ່ເລກຊ້ຳກັນເມື່ອຕັດ "ຕູ້" ອອກ)
ໃໝ່: ຊ່ອງນັບຕໍ່ເນື່ອງທັງໂຊນ → A-05, A-17 ... ກົງກັບປ້າຍຈິງ (ເບິ່ງ images/)

ບໍ່ມີການປ່ຽນໂຄງສ້າງຕາຕະລາງ — ປ່ຽນສະເພາະຄ່າ cabinet (= ຊັ້ນວາງ) ແລະ position.
Asset ທີ່ຝາກໄວ້ຢູ່ແລ້ວຍັງຢູ່ບ່ອນເກົ່າ (FK ບໍ່ຖືກແຕະ) — ປ່ຽນແຕ່ປ້າຍທີ່ສະແດງ.
"""

from django.db import migrations

PER_ROW = {"A": 5, "B": 6, "V": 2}
DEFAULT_PER_ROW = 6
LEGACY_PER_CABINET = 12
# ຂຽນຄ່າຊົ່ວຄາວດ້ວຍ offset ສູງກ່ອນ — ກັນຊົນກັບ unique constraint ລະຫວ່າງທາງ
# (ໃຊ້ເລກລົບບໍ່ໄດ້: PositiveSmallIntegerField ມີ CHECK constraint >= 0)
TEMP_OFFSET = 1000


def _renumber(StorageSlot, zone, order_fields, per_row):
    slots = list(StorageSlot.objects.filter(zone=zone).order_by(*order_fields))
    for index, slot in enumerate(slots, start=1):
        slot.position = TEMP_OFFSET + index
    StorageSlot.objects.bulk_update(slots, ["position"])
    for index, slot in enumerate(slots, start=1):
        slot.position = index
        slot.cabinet = (index - 1) // per_row + 1
    StorageSlot.objects.bulk_update(slots, ["position", "cabinet"])


def renumber_forward(apps, schema_editor):
    """ນັບຊ່ອງຕໍ່ເນື່ອງພາຍໃນໂຊນ ແລ້ວຄິດໄລ່ຊັ້ນວາງຄືນຕາມຄວາມກວ້າງແຖວຈິງ"""
    StorageSlot = apps.get_model("asset_intake", "StorageSlot")
    for zone in StorageSlot.objects.values_list("zone", flat=True).distinct():
        _renumber(
            StorageSlot,
            zone,
            ["cabinet", "position", "pk"],
            PER_ROW.get(zone, DEFAULT_PER_ROW),
        )


def renumber_backward(apps, schema_editor):
    """ຄືນເປັນແບບ ຕູ້ × 12 ຊ່ອງ"""
    StorageSlot = apps.get_model("asset_intake", "StorageSlot")
    for zone in StorageSlot.objects.values_list("zone", flat=True).distinct():
        _renumber(StorageSlot, zone, ["position", "pk"], LEGACY_PER_CABINET)


class Migration(migrations.Migration):

    dependencies = [
        ("asset_intake", "0004_storageslot_asset_storage_slot"),
    ]

    operations = [
        migrations.RunPython(renumber_forward, renumber_backward),
    ]
