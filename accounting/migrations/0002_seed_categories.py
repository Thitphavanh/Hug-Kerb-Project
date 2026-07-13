from django.db import migrations


DEFAULT_CATEGORIES = [
    ("IN", "ລາຍຮັບຄ່າບໍລິການ", "#10b981", 10),
    ("IN", "ຂາຍສິນຄ້າ/ອຸປະກອນ", "#22d3ee", 20),
    ("IN", "ເງິນລົງທຶນ", "#8b5cf6", 30),
    ("IN", "ລາຍຮັບອື່ນໆ", "#38bdf8", 90),
    ("OUT", "ອຸປະກອນ/ນ້ຳຢາ", "#f97316", 10),
    ("OUT", "ຄ່າເຊົ່າ", "#fb7185", 20),
    ("OUT", "ຄ່ານ້ຳ/ໄຟ/ອິນເຕີເນັດ", "#eab308", 30),
    ("OUT", "ເງິນເດືອນ/ຄ່າແຮງງານ", "#ec4899", 40),
    ("OUT", "ການຕະຫຼາດ/ໂຄສະນາ", "#a855f7", 50),
    ("OUT", "ຄ່າສ້ອມແປງ/ບຳລຸງ", "#f43f5e", 60),
    ("OUT", "ຄ່າຂົນສົ່ງ", "#06b6d4", 70),
    ("OUT", "ລາຍຈ່າຍອື່ນໆ", "#ef4444", 90),
]


def seed_categories(apps, schema_editor):
    AccountCategory = apps.get_model("accounting", "AccountCategory")
    for transaction_type, name, color, sort_order in DEFAULT_CATEGORIES:
        AccountCategory.objects.get_or_create(
            transaction_type=transaction_type,
            name=name,
            defaults={"color": color, "sort_order": sort_order},
        )


def remove_seeded_categories(apps, schema_editor):
    AccountCategory = apps.get_model("accounting", "AccountCategory")
    AccountCategory.objects.filter(name__in=[row[1] for row in DEFAULT_CATEGORIES]).delete()


class Migration(migrations.Migration):
    dependencies = [("accounting", "0001_initial")]
    operations = [migrations.RunPython(seed_categories, remove_seeded_categories)]

