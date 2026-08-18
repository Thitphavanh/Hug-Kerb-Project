"""ການຫັກສະຕັອກອັດຕະໂນມັດ (Scope 2.1)

ຈຸດຫັກ: ຕອນບິນຊຳລະຄົບຄັ້ງທຳອິດ — ຈຸດດຽວກັບທີ່ປະທັບ Stamp.
ເລືອກຈຸດນີ້ເພາະມັນເປັນການປ່ຽນສະຖານະທີ່ຄຸມ idempotency ໄວ້ແລ້ວໃນ pos.services
ຈຶ່ງບໍ່ມີທາງຫັກສະຕັອກສອງເທື່ອຈາກບິນໃບດຽວ.
"""

from collections import defaultdict

from django.db import transaction

from .models import ServiceSupply, StockMovement, Supply


@transaction.atomic
def consume_supplies_for_order(order):
    """ຫັກອຸປະກອນທີ່ບໍລິການໃນບິນນີ້ໃຊ້ ແລ້ວຄືນລາຍການ StockMovement ທີ່ສ້າງ

    ຮຽກຊ້ຳກໍປອດໄພ: ຖ້າບິນນີ້ເຄີຍຫັກແລ້ວຈະບໍ່ຫັກອີກ.
    """
    if StockMovement.objects.filter(order=order).exists():
        return []

    service_ids = [
        item.service_type_id for item in order.items.all() if item.service_type_id
    ]
    if not service_ids:
        return []

    # ລວມຈຳນວນຕໍ່ອຸປະກອນກ່ອນ — ບໍລິການຫຼາຍລາຍການອາດໃຊ້ອຸປະກອນຕົວດຽວກັນ
    # ຢາກໃຫ້ອອກມາເປັນແຖວດຽວຕໍ່ອຸປະກອນ ອ່ານປະຫວັດງ່າຍກວ່າ
    needed = defaultdict(int)
    recipes = ServiceSupply.objects.filter(service_type_id__in=service_ids)
    quantity_by_service = defaultdict(int)
    for item in order.items.all():
        if item.service_type_id:
            quantity_by_service[item.service_type_id] += item.quantity

    for recipe in recipes:
        units = quantity_by_service.get(recipe.service_type_id, 0)
        if units:
            needed[recipe.supply_id] += recipe.quantity_per_unit * units

    # ຍອດຄົງເຫຼືອກ່ອນຫັກ — ໃຊ້ບອກວ່າອຸປະກອນໃດບໍ່ພໍ ແລ້ວຈະຕິດລົບ
    # ບໍ່ຢຸດການຫັກ: ຂອງຖືກໃຊ້ໄປແທ້ແລ້ວໜ້າຮ້ານ ບັນຊີສະຕັອກຕ້ອງສະທ້ອນຄວາມຈິງ
    # ແຕ່ຕ້ອງບັນທຶກໄວ້ໃນໝາຍເຫດ ບໍ່ດັ່ງນັ້ນຍອດຕິດລົບຈະໂຜ່ມາໂດຍບໍ່ຮູ້ສາເຫດ
    on_hand = dict(
        Supply.objects.filter(pk__in=needed).values_list("pk", "quantity_on_hand")
    )

    movements = []
    for supply_id, quantity in sorted(needed.items()):
        available = on_hand.get(supply_id, 0)
        note = f"ຕັດອັດຕະໂນມັດຈາກບິນ {order.order_number}"
        if quantity > available:
            note += f" — ສະຕັອກບໍ່ພໍ (ເຫຼືອ {available}, ຕ້ອງການ {quantity})"
        movements.append(
            StockMovement.objects.create(
                supply_id=supply_id,
                movement_type=StockMovement.MovementType.OUT,
                quantity=quantity,
                order=order,
                note=note,
            )
        )
    return movements
