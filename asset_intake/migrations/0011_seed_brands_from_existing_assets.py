"""ຍ້າຍຍີ່ຫໍ້/ລຸ້ນທີ່ມີຢູ່ແລ້ວເຂົ້າຕາຕະລາງໃໝ່

ດຶງຈາກ 2 ບ່ອນ: ລາຍການທີ່ເຄີຍຝັງແຂງໄວ້ໃນ template ຂອງໜ້າ POS
ແລະ ຄູ່ເກີບຈິງທີ່ຮ້ານຮັບເຂົ້າມາແລ້ວ — ຈຶ່ງບໍ່ມີຂໍ້ມູນເກົ່າຕົກຫຼົ່ນ.

ຈັບຄູ່ຊື່ແບບບໍ່ສົນຕົວພິມໃຫຍ່-ນ້ອຍ ເພື່ອລວມ "nike" ກັບ "Nike" ເປັນອັນດຽວ.
"""

from django.db import migrations

# ລາຍການທີ່ເຄີຍຢູ່ໃນ pos/templates/pos/create_order.html
SEED_BRANDS = ["Nike", "Adidas", "Jordan", "New Balance", "Converse", "Vans"]


def seed(apps, schema_editor):
    Brand = apps.get_model("asset_intake", "Brand")
    ShoeModel = apps.get_model("asset_intake", "ShoeModel")
    Asset = apps.get_model("asset_intake", "Asset")

    brands = {}

    def brand_for(raw_name, order):
        key = raw_name.strip().lower()
        if not key:
            return None
        if key not in brands:
            brands[key] = Brand.objects.create(name=raw_name.strip(), sort_order=order)
        return brands[key]

    for index, name in enumerate(SEED_BRANDS):
        brand_for(name, index)

    # ຍີ່ຫໍ້/ລຸ້ນຈາກຄູ່ເກີບຈິງ — ອັນທີ່ບໍ່ຢູ່ໃນລາຍການຂ້າງເທິງຈະຖືກເພີ່ມຕໍ່ທ້າຍ
    seen_models = set()
    for asset in Asset.objects.exclude(brand="").order_by("pk"):
        brand = brand_for(asset.brand, 50)
        if brand is None:
            continue
        model_name = (asset.model_name or "").strip()
        if not model_name:
            continue
        key = (brand.pk, model_name.lower())
        if key in seen_models:
            continue
        seen_models.add(key)
        ShoeModel.objects.get_or_create(brand=brand, name=model_name)


def unseed(apps, schema_editor):
    apps.get_model("asset_intake", "ShoeModel").objects.all().delete()
    apps.get_model("asset_intake", "Brand").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("asset_intake", "0010_brand_shoemodel")]
    operations = [migrations.RunPython(seed, unseed)]
