"""ໜ້າ public ສຳລັບລູກຄ້າ (Customer Portal) — ເຂົ້າຜ່ານ QR ບໍ່ຕ້ອງ login
ແຕ່ຕ້ອງຢືນຢັນເບີໂທທີ່ລົງທະບຽນກັບຮ້ານກ່ອນ ຈຶ່ງຈະເຫັນຂໍ້ມູນ"""

import re

from django.shortcuts import get_object_or_404, redirect, render

from asset_intake.models import Asset
from media_backup.models import MediaFile

from .models import MemberCard

# ລຳດັບຂັ້ນຕອນທີ່ສະແດງໃນ timeline (RETURNED ຄືຈຸດສຸດທ້າຍ)
STATUS_FLOW = [
    Asset.Status.RECEIVED,
    Asset.Status.CLEANING,
    Asset.Status.REPAIRING,
    Asset.Status.READY,
    Asset.Status.RETURNED,
]


def _phone_digits(phone):
    return re.sub(r"\D", "", phone or "")


def _phone_matches(entered, registered):
    """ທຽບເບີໂທແບບຍືດຫຍຸ່ນ — ທຽບ 8 ໂຕທ້າຍ ເພື່ອຮອງຮັບ +856/020 ທີ່ຂຽນຕ່າງກັນ"""
    a, b = _phone_digits(entered), _phone_digits(registered)
    if len(a) < 6 or len(b) < 6:
        return False
    return a[-8:] == b[-8:]


def _session_key(asset):
    return f"portal_ok_{asset.pk}"


def lookup(request):
    """ໜ້າຄົ້ນຫາ — ລູກຄ້າຕື່ມເລກໃບຮັບເຄື່ອງ (TK-…) + ເບີໂທທີ່ລົງທະບຽນ"""
    error = None
    if request.method == "POST":
        ticket = request.POST.get("ticket_number", "").strip()
        phone = request.POST.get("phone", "").strip()
        asset = (
            Asset.objects.select_related("customer")
            .filter(ticket_number__iexact=ticket)
            .first()
        )
        if asset and _phone_matches(phone, asset.customer.phone):
            request.session[_session_key(asset)] = True
            return redirect("digital_member:track", token=asset.public_token)
        error = "ບໍ່ພົບຂໍ້ມູນ ຫຼື ເບີໂທບໍ່ກົງກັບທີ່ລົງທະບຽນ — ກະລຸນາກວດຄືນ"
    return render(request, "digital_member/lookup.html", {"error": error})


def track_asset(request, token):
    """ໜ້າຕິດຕາມສະຖານະເກີບ — ເປີດຈາກ QR ຫຼັງໃບຮັບເຄື່ອງ ຫຼື ລິ້ງໃນຂໍ້ຄວາມແຈ້ງເຕືອນ"""
    asset = get_object_or_404(
        Asset.objects.select_related("customer"), public_token=token
    )

    # ດ່ານຢືນຢັນຕົວຕົນ: ຕ້ອງຕື່ມເບີໂທທີ່ລົງທະບຽນກ່ອນ (ຈື່ໄວ້ໃນ session)
    if not request.session.get(_session_key(asset)):
        error = None
        if request.method == "POST":
            phone = request.POST.get("phone", "").strip()
            if _phone_matches(phone, asset.customer.phone):
                request.session[_session_key(asset)] = True
                return redirect("digital_member:track", token=token)
            error = "ເບີໂທບໍ່ກົງກັບທີ່ລົງທະບຽນກັບຮ້ານ — ກະລຸນາລອງໃໝ່"
        return render(
            request,
            "digital_member/verify.html",
            {"asset": asset, "error": error},
        )

    current_index = STATUS_FLOW.index(asset.status) if asset.status in STATUS_FLOW else 0
    timeline = [
        {
            "label": Asset.Status(status).label,
            "is_done": i < current_index,
            "is_current": i == current_index,
        }
        for i, status in enumerate(STATUS_FLOW)
    ]

    member_card = MemberCard.objects.filter(
        customer=asset.customer, is_active=True
    ).first()

    context = {
        "asset": asset,
        "timeline": timeline,
        "is_ready": asset.status == Asset.Status.READY,
        "is_returned": asset.status == Asset.Status.RETURNED,
        "before_media": asset.media_files.filter(
            stage=MediaFile.Stage.BEFORE, media_type=MediaFile.MediaType.IMAGE
        )[:4],
        "after_media": asset.media_files.filter(
            stage=MediaFile.Stage.AFTER, media_type=MediaFile.MediaType.IMAGE
        )[:4],
        "member_card": member_card,
    }
    return render(request, "digital_member/track.html", context)


def member_card_view(request, card_number):
    """ບັດສະມາຊິກດິຈິຕອລ + ຄະແນນສະສົມ"""
    card = get_object_or_404(
        MemberCard.objects.select_related("customer"),
        card_number=card_number,
        is_active=True,
    )
    return render(
        request,
        "digital_member/member_card.html",
        {"card": card, "transactions": card.transactions.all()[:10]},
    )


def logout_portal(request, token):
    """ອອກຈາກລະບົບ (ລຶບ session ສຳລັບໃບບິນນີ້)"""
    asset = get_object_or_404(Asset, public_token=token)
    session_key = _session_key(asset)
    if session_key in request.session:
        del request.session[session_key]
    return redirect("digital_member:lookup")
