"""ຊິງໂຄຣໄນ OrderItem → AssetService

ຕອນ POS ເປີດບິນ ມັນສ້າງ OrderItem (asset + service_type) ຢູ່ແລ້ວ.
ໃຊ້ signal ແທນການແກ້ທຸກຈຸດທີ່ສ້າງ OrderItem ເພື່ອໃຫ້ຄຸມໄດ້ທຸກເສັ້ນທາງ
(POS, ໜ້າແກ້ໄຂອໍເດີ, Django Admin, ແລະໂຄດທີ່ຈະເພີ່ມພາຍຫຼັງ).
"""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="pos.OrderItem", dispatch_uid="orderitem_to_assetservice")
def create_asset_service(sender, instance, created, **kwargs):
    """ສ້າງວຽກບໍລິການໃຫ້ຄູ່ເກີບ ເມື່ອມີການຂາຍບໍລິການໃຫ້ຄູ່ນັ້ນ"""
    if not created:
        return
    if not instance.asset_id or not instance.service_type_id:
        return

    from .models import AssetService

    AssetService.objects.get_or_create(
        asset_id=instance.asset_id,
        service_type_id=instance.service_type_id,
        defaults={
            "name": instance.service_type.name,
            "work_type": instance.service_type.work_type,
        },
    )
