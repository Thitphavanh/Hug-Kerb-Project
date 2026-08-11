# ສ້າງບໍລິການ "ຮັບຊື້ເກີບມືສອງ" ອັດຕະໂນມັດ — ຮ້ານໃຊ້ AI ຊ່ວຍປະເມີນສະພາບ + ລາຄາຮັບຊື້
# ລາຄາ 0 ເພາະຮ້ານເປັນຝ່າຍຈ່າຍເງິນຊື້ ບໍ່ແມ່ນເກັບເງິນລູກຄ້າ
from django.db import migrations

BUYBACK_SERVICE_NAME = "Buy-back Evaluation"


def create_buyback_service(apps, schema_editor):
    ServiceType = apps.get_model("pos", "ServiceType")
    ServiceType.objects.get_or_create(
        name=BUYBACK_SERVICE_NAME,
        defaults={"category": "buyback", "price": 0, "is_active": True},
    )


def remove_buyback_service(apps, schema_editor):
    ServiceType = apps.get_model("pos", "ServiceType")
    ServiceType.objects.filter(
        name=BUYBACK_SERVICE_NAME, order_items__isnull=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0005_alter_servicetype_category"),
    ]

    operations = [
        migrations.RunPython(create_buyback_service, remove_buyback_service),
    ]
