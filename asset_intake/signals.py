"""ຊິງໂຄຣໄນ OrderItem → AssetService

ຕອນ POS ເປີດບິນ ມັນສ້າງ OrderItem (asset + service_type) ຢູ່ແລ້ວ.
ໃຊ້ signal ແທນການແກ້ທຸກຈຸດທີ່ສ້າງ OrderItem ເພື່ອໃຫ້ຄຸມໄດ້ທຸກເສັ້ນທາງ
(POS, ໜ້າແກ້ໄຂອໍເດີ, Django Admin, ແລະໂຄດທີ່ຈະເພີ່ມພາຍຫຼັງ).
"""

from django.db.models.signals import post_delete, post_save
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


@receiver(
    post_delete, sender="pos.OrderItem", dispatch_uid="orderitem_drop_assetservice"
)
def drop_asset_service(sender, instance, **kwargs):
    """ເອົາບໍລິການອອກຈາກບິນ → ເອົາ card ອອກຈາກກະດານນຳ

    ລຶບສະເພາະ card ທີ່ຍັງບໍ່ໄດ້ເລີ່ມເຮັດ (pending): ວຽກທີ່ຊ່າງລົງມືແລ້ວ ຫຼືເຮັດແລ້ວ
    ຮັກສາໄວ້ເປັນປະຫວັດ ເຖິງແມ່ນລາຍການຈະຫຼຸດອອກຈາກບິນ.
    ຖ້າຍັງມີລາຍການອື່ນຜູກ asset+service ຄູ່ນີ້ຢູ່ ບໍ່ຕ້ອງລຶບ.
    """
    if not instance.asset_id or not instance.service_type_id:
        return

    from pos.models import OrderItem

    still_ordered = (
        OrderItem.objects.filter(
            asset_id=instance.asset_id, service_type_id=instance.service_type_id
        )
        .exclude(pk=instance.pk)
        .exists()
    )
    if still_ordered:
        return

    from .models import Asset, AssetService

    deleted, _ = AssetService.objects.filter(
        asset_id=instance.asset_id,
        service_type_id=instance.service_type_id,
        status=AssetService.Status.PENDING,
    ).delete()

    # ຫຼຸດ card ອອກແລ້ວ ວຽກທີ່ເຫຼືອອາດຈົບໝົດແລ້ວ → ຄິດສະຖານະຄູ່ເກີບຄືນໃໝ່
    # (asset ອາດຖືກລຶບໄປພ້ອມກັນ ຖ້າ cascade ມາຈາກການລຶບ asset)
    if deleted:
        asset = Asset.objects.filter(pk=instance.asset_id).first()
        if asset is not None:
            asset.rollup_status()
