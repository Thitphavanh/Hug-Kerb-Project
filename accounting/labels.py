from django.utils.translation import get_language


CATEGORY_ENGLISH_NAMES = {
    "ລາຍຮັບຄ່າບໍລິການ": "Service income",
    "ຂາຍສິນຄ້າ/ອຸປະກອນ": "Product and equipment sales",
    "ເງິນລົງທຶນ": "Capital contribution",
    "ລາຍຮັບອື່ນໆ": "Other income",
    "ອຸປະກອນ/ນ້ຳຢາ": "Supplies and cleaning products",
    "ຄ່າເຊົ່າ": "Rent",
    "ຄ່ານ້ຳ/ໄຟ/ອິນເຕີເນັດ": "Water, electricity and internet",
    "ເງິນເດືອນ/ຄ່າແຮງງານ": "Salaries and wages",
    "ການຕະຫຼາດ/ໂຄສະນາ": "Marketing and advertising",
    "ຄ່າສ້ອມແປງ/ບຳລຸງ": "Repairs and maintenance",
    "ຄ່າຂົນສົ່ງ": "Delivery and transport",
    "ລາຍຈ່າຍອື່ນໆ": "Other expenses",
}


def localized_category_name(category):
    if (get_language() or "").startswith("en"):
        return CATEGORY_ENGLISH_NAMES.get(category.name, category.name)
    return category.name

