"""ຖອດລະຫັດຄ່າທີ່ສະແກນໄດ້ ໃຫ້ກາຍເປັນ Asset ຫຼື Order

ແຍກອອກມາເປັນໂມດູນຕ່າງຫາກ ເພາະມີຫຼາຍໜ້າໃຊ້ຮ່ວມກັນ:
ໜ້າເປີດບິນ (ຜ່ານ API scan_lookup) ແລະ ໜ້າບິນຄ້າງ (ຄົ້ນຫາດ້ວຍການສະແກນ).
"""

import re

from .models import Order


def resolve_scan_code(code):
    """ຄືນ (asset, order) ຈາກຄ່າດຽວທີ່ສະແກນ/ພິມເຂົ້າມາ

    ຮັບໄດ້ 4 ຮູບແບບ:
      1. URL portal ລູກຄ້າ  .../t/<public_token>/
      2. URL ປ້າຍແທັກຫ້ອຍເກີບ  .../<asset_pk>/
      3. ເລກອໍເດີ  ORD...
      4. ເລກໃບຮັບເຄື່ອງ TK... ຫຼື public_token ລ້ວນ

    ຄ່າໃດຫາບໍ່ພົບຈະຄືນເປັນ None — ຜູ້ເອີ້ນເປັນຜູ້ຕັດສິນວ່າຈະເຮັດຫຍັງຕໍ່
    """
    from asset_intake.models import Asset

    code = (code or "").strip()
    if not code:
        return None, None

    assets = Asset.objects.select_related("customer")

    if code.lower().startswith(("http://", "https://")):
        match = re.search(r"/t/([A-Za-z0-9_-]+)/?", code)
        if match:
            return assets.filter(public_token=match.group(1)).first(), None
        # ປ້າຍແທັກ: URL ໜ້າລາຍລະອຽດ ລົງທ້າຍດ້ວຍ /<pk>/
        match = re.search(r"/(\d+)/?(?:[?#].*)?$", code)
        if match:
            return assets.filter(pk=int(match.group(1))).first(), None
        return None, None

    if code.upper().startswith("ORD"):
        order = Order.objects.select_related("customer").filter(
            order_number__iexact=code
        ).first()
        return None, order

    asset = assets.filter(ticket_number__iexact=code).first()
    if asset is None:
        asset = assets.filter(public_token=code).first()
    return asset, None


def open_order_for_scan(code):
    """ຫາບິນທີ່ຍັງເປີດຢູ່ຈາກຄ່າທີ່ສະແກນ — ໃຊ້ໃນໜ້າ "ບິນຄ້າງ"

    ສະແກນປ້າຍເກີບ 1 ຄູ່ → ໄດ້ບິນທີ່ຄູ່ນັ້ນຢູ່. ຖ້າເກີບຄູ່ດຽວປະກົດໃນຫຼາຍບິນ
    (ລູກຄ້າເອົາມາຊັກຊ້ຳ) ເອົາບິນທີ່ຍັງເປີດ ແລະ ໃໝ່ສຸດ.
    """
    asset, order = resolve_scan_code(code)

    if order is not None:
        return order if order.status in Order.OPEN_STATUSES else None

    if asset is not None:
        return (
            Order.objects.filter(
                items__asset=asset, status__in=Order.OPEN_STATUSES
            )
            .order_by("-created_at")
            .first()
        )

    return None
