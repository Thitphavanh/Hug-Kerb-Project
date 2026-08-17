from django.db import migrations


# ການຍ້າຍເງິນສົດເຂົ້າບັນຊີທະນາຄານຕ້ອງໃຊ້ 2 ໝວດ ຊື່ດຽວກັນ ຄົນລະປະເພດ:
# ຝັ່ງ OUT ຫັກເງິນອອກຈາກກຳປັ່ນ, ຝັ່ງ IN ເຂົ້າບັນຊີທະນາຄານ.
# ທັງສອງຖືກໝາຍວ່າ is_internal_transfer ຈຶ່ງບໍ່ຖືກນັບເປັນລາຍຮັບ/ລາຍຈ່າຍ.
TRANSFER_CATEGORY_NAME = "ຍ້າຍເງິນເຂົ້າບັນຊີທະນາຄານ"
COLOR = "#64748b"


def seed(apps, schema_editor):
    AccountCategory = apps.get_model("accounting", "AccountCategory")
    for transaction_type in ("IN", "OUT"):
        category, _created = AccountCategory.objects.get_or_create(
            transaction_type=transaction_type,
            name=TRANSFER_CATEGORY_NAME,
            defaults={"color": COLOR, "sort_order": 95},
        )
        if not category.is_internal_transfer:
            category.is_internal_transfer = True
            category.save(update_fields=["is_internal_transfer"])


def unseed(apps, schema_editor):
    AccountCategory = apps.get_model("accounting", "AccountCategory")
    AccountCategory.objects.filter(
        name=TRANSFER_CATEGORY_NAME, is_internal_transfer=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0004_accountcategory_is_internal_transfer_and_more")
    ]
    operations = [migrations.RunPython(seed, unseed)]
