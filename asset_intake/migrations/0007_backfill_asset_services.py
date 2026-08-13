"""ສ້າງແຖວ AssetService ຈາກ OrderItem ທີ່ມີຢູ່ແລ້ວ

ຮ້ານບັນທຶກໄວ້ຢູ່ແລ້ວວ່າເກີບແຕ່ລະຄູ່ຊື້ບໍລິການຫຍັງແດ່ (OrderItem.asset + service_type)
ຈຶ່ງ backfill ໄດ້ໂດຍບໍ່ຕ້ອງພິມຄືນໃໝ່.

ສະຖານະເລີ່ມຕົ້ນອິງຕາມສະຖານະປັດຈຸບັນຂອງຄູ່ນັ້ນ ເພື່ອບໍ່ໃຫ້ວຽກທີ່ເຮັດແລ້ວຍ້ອນກັບ:
  ready / returned → ວຽກທັງໝົດຖືວ່າແລ້ວ
  cleaning         → ວຽກຊັກກຳລັງເຮັດ, ວຽກອື່ນລໍຖ້າ
  repairing        → ວຽກສ້ອມກຳລັງເຮັດ, ວຽກອື່ນລໍຖ້າ
  received         → ລໍຖ້າໝົດ
"""

from django.db import migrations


def backfill(apps, schema_editor):
    OrderItem = apps.get_model("pos", "OrderItem")
    AssetService = apps.get_model("asset_intake", "AssetService")

    existing = set(
        AssetService.objects.values_list("asset_id", "service_type_id")
    )

    new_rows = []
    seen = set()
    items = OrderItem.objects.filter(
        asset_id__isnull=False, service_type_id__isnull=False
    ).select_related("asset", "service_type")

    for item in items:
        key = (item.asset_id, item.service_type_id)
        if key in existing or key in seen:
            continue
        seen.add(key)

        asset_status = item.asset.status
        work_type = item.service_type.work_type

        if asset_status in ("ready", "returned"):
            status = "done"
        elif asset_status == "cleaning" and work_type == "wash":
            status = "in_progress"
        elif asset_status == "repairing" and work_type == "repair":
            status = "in_progress"
        else:
            status = "pending"

        new_rows.append(
            AssetService(
                asset_id=item.asset_id,
                service_type_id=item.service_type_id,
                name=item.service_type.name,
                work_type=work_type,
                status=status,
                started_at=item.asset.intake_date if status != "pending" else None,
                finished_at=item.asset.updated_at if status == "done" else None,
            )
        )

    AssetService.objects.bulk_create(new_rows)


def unbackfill(apps, schema_editor):
    AssetService = apps.get_model("asset_intake", "AssetService")
    AssetService.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("asset_intake", "0006_alter_storageslot_cabinet_assetservice"),
        ("pos", "0008_servicetype_work_type_defaults"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
