from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _, gettext_noop
from django.views.decorators.http import require_POST

from ai_mart_grading.models import Assessment, ChecklistItem
from crm.models import Customer
from media_backup.models import MediaFile
from media_backup.services import store_uploads
from notifications.services import build_wa_link

from .forms import IntakeForm
from .models import Asset, AssetService, Brand, ShoeModel, StorageSlot, build_zone_rows
from .utils import absolute_url, qr_data_uri


CHECKLIST_LABELS = {
    "ຮອຍເປື້ອນ/ຄວາມສະອາດຂອງໜ້າເກີບ": gettext_noop("Upper cleanliness and stains"),
    "Laces condition": gettext_noop("Laces condition"),
    "ຮອຍຈີກ/ຮອຍແຕກຂອງວັດສະດຸໜ້າເກີບ": gettext_noop("Upper material tears or cracks"),
    "Upper / body condition": gettext_noop("Upper / body condition"),
    "ສີຊີດຈາງ/ປ່ຽນສີ": gettext_noop("Fading or discoloration"),
    "Sole condition": gettext_noop("Sole condition"),
    "ການສຶກຫຼໍ່ຂອງພື້ນນອກ (Outsole)": gettext_noop("Outsole wear"),
    "Insole condition": gettext_noop("Insole condition"),
    "Midsole ແຕກ/ຍຸບ/ເສື່ອມ": gettext_noop("Midsole cracks, compression, or deterioration"),
    "Color condition": gettext_noop("Color condition"),
    "ພື້ນເຫຼືອງ (Oxidation)": gettext_noop("Sole yellowing (oxidation)"),
    "ສະພາບພື້ນໃນ ແລະ ກິ່ນ": gettext_noop("Insole condition and odor"),
    "ສາຍເກີບຄົບ ແລະ ສະພາບດີ": gettext_noop("Laces completeness and condition"),
    "ກ່ອງ/ອຸປະກອນເສີມຄົບຖ້ວນ": gettext_noop("Box and accessories completeness"),
    "ການກວດຄວາມແທ້ເບື້ອງຕົ້ນ (Authenticity)": gettext_noop("Preliminary authenticity check"),
}

# ບໍລິການທີ່ໃຊ້ AI Grading checklist — ບໍລິການອື່ນ (ຊັກ/ສ້ອມ/ສະປາ) ບໍ່ຕ້ອງການອັນນີ້
AI_GRADING_SERVICE_NAME = "AI Condition Report"

# The AI supplies only the cleanliness score. Service names and prices always
# come from the shop-managed ServiceType table.
CLEANLINESS_CHECKLIST_NAMES = {
    "ຮອຍເປື້ອນ/ຄວາມສະອາດຂອງໜ້າເກີບ",
    "Upper cleanliness and stains",
}


def build_care_price_recommendation(assessment):
    """Map a completed AI cleanliness score to an active shop price tier.

    The recommendation is intentionally deterministic: AI does not generate
    money. Active primary services are sorted by their configured price, then
    light/moderate/heavy dirt selects the low/middle/high tier respectively.
    """
    if not assessment or assessment.status != Assessment.Status.DONE:
        return None

    from pos.models import ServiceType

    primary_services = list(
        ServiceType.objects.filter(
            is_active=True,
            category=ServiceType.Category.PRIMARY,
        ).order_by("price", "pk")
    )
    if not primary_services:
        return None

    assessment_items = list(assessment.items.select_related("checklist_item"))
    if not assessment_items:
        return None

    cleanliness_item = next(
        (
            item
            for item in assessment_items
            if item.checklist_item.name in CLEANLINESS_CHECKLIST_NAMES
        ),
        None,
    )
    if cleanliness_item is None:
        cleanliness_item = next(
            (
                item
                for item in assessment_items
                if "cleanliness" in item.checklist_item.name.lower()
                or "stain" in item.checklist_item.name.lower()
                or "ເປື້ອນ" in item.checklist_item.name
            ),
            None,
        )

    if cleanliness_item and cleanliness_item.checklist_item.max_score:
        percentage = (
            float(cleanliness_item.score)
            / cleanliness_item.checklist_item.max_score
            * 100
        )
    else:
        # Legacy assessments may not have a dedicated cleanliness row. Use a
        # weighted checklist average so an existing completed report can still
        # produce a useful estimate.
        maximum = sum(
            item.checklist_item.max_score for item in assessment_items
        )
        if not maximum:
            return None
        percentage = (
            sum(float(item.score) for item in assessment_items) / maximum * 100
        )

    percentage = max(0, min(100, round(percentage)))
    if percentage >= 80:
        dirt_level = "light"
        dirt_label = _("Light dirt")
        service = primary_services[0]
    elif percentage >= 50:
        dirt_level = "moderate"
        dirt_label = _("Moderate dirt")
        service = primary_services[len(primary_services) // 2]
    else:
        dirt_level = "heavy"
        dirt_label = _("Heavy dirt")
        service = primary_services[-1]

    return {
        "dirt_level": dirt_level,
        "dirt_label": dirt_label,
        "cleanliness_percentage": percentage,
        "service": service,
        "price": service.price,
    }

BUYBACK_PHOTO_REQUIREMENTS = (
    (
        MediaFile.CaptureAngle.FRONT,
        gettext_noop("Front / toe box"),
        gettext_noop("Show both shoes, toe boxes, laces, and overall shape."),
        True,
    ),
    (
        MediaFile.CaptureAngle.HEEL,
        gettext_noop("Heel / rear"),
        gettext_noop("Show heel logos, stitching, and rear sole wear."),
        True,
    ),
    (
        MediaFile.CaptureAngle.SIDE,
        gettext_noop("Side profile"),
        gettext_noop("Show materials, Swoosh, stitching, and midsole."),
        True,
    ),
    (
        MediaFile.CaptureAngle.OUTSOLE,
        gettext_noop("Outsole"),
        gettext_noop("Show the complete tread and wear on both soles."),
        True,
    ),
    (
        MediaFile.CaptureAngle.SIZE_LABEL,
        gettext_noop("Size label / SKU"),
        gettext_noop("Make the SKU, size, dates, and QR code readable."),
        True,
    ),
    (
        MediaFile.CaptureAngle.INNER,
        gettext_noop("Inner side / insole"),
        gettext_noop("Show the inner side, insole logo, and inner stitching."),
        False,
    ),
    (
        MediaFile.CaptureAngle.BOX_ACCESSORIES,
        gettext_noop("Box and accessories"),
        gettext_noop("Show the box label, receipt, spare laces, and accessories."),
        False,
    ),
    (
        MediaFile.CaptureAngle.DEFECT,
        gettext_noop("Defect close-up"),
        gettext_noop("Add a close-up of any stain, tear, crack, or repair."),
        False,
    ),
)


@login_required
def intake_list(request):
    assets = Asset.objects.select_related("customer").exclude(
        status=Asset.Status.RETURNED
    )
    status_labels = {
        Asset.Status.RECEIVED: _("Received"),
        Asset.Status.CLEANING: _("Cleaning"),
        Asset.Status.REPAIRING: _("Repairing"),
        Asset.Status.READY: _("Ready for pickup"),
        Asset.Status.RETURNED: _("Completed"),
    }
    for asset in assets:
        asset.localized_status = status_labels.get(asset.status, asset.status)
    return render(
        request,
        "asset_intake/intake_list.html",
        {"active_nav": "intake", "assets": assets},
    )


@login_required
def intake_create(request):
    if request.method == "POST":
        form = IntakeForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            # ພະນັກງານເລືອກລູກຄ້າເກົ່າຈາກຊ່ອງຄົ້ນຫາ → ຜູກດ້ວຍ id ກ່ອນ
            # ບໍ່ດັ່ງນັ້ນການແກ້ເບີໂທຈະໄປສ້າງລູກຄ້າຊ້ຳຂຶ້ນມາອີກຄົນ
            customer = (
                Customer.objects.filter(pk=data["customer_id"]).first()
                if data.get("customer_id")
                else None
            )
            if customer is None:
                customer, _created = Customer.objects.get_or_create(
                    phone=data["customer_phone"],
                    defaults={"name": data["customer_name"]},
                )

            updates = []
            if customer.name != data["customer_name"]:
                customer.name = data["customer_name"]
                updates.append("name")
            if customer.phone != data["customer_phone"]:
                customer.phone = data["customer_phone"]
                updates.append("phone")
            if updates:
                customer.save(update_fields=updates)

            asset = Asset.objects.create(
                customer=customer,
                brand=data["brand"],
                model_name=data["model_name"],
                color=data["color"],
                size=data["size"],
                condition_note=data["condition_note"],
                pickup_date=data["pickup_date"],
            )
            _saved, upload_errors = store_uploads(
                asset=asset,
                files=request.FILES.getlist("photos"),
                stage=MediaFile.Stage.BEFORE,
                uploaded_by=request.user,
            )
            for error in upload_errors:
                messages.error(request, error)

            messages.success(
                request,
                _("Intake saved successfully — Ticket #%(ticket)s")
                % {"ticket": asset.ticket_number},
            )
            return redirect("asset_intake:detail", pk=asset.pk)
    else:
        form = IntakeForm()

    return render(
        request,
        "asset_intake/intake_form.html",
        {
            "active_nav": "pos",
            "form": form,
            # ຊຸດລູກຄ້າຕັ້ງຕົ້ນ ໃຫ້ຊ່ອງຄົ້ນຫາຂຶ້ນຜົນທັນທີ ກ່ອນ API ຈະຕອບ
            "customer_seed": [
                {"id": pk, "name": name, "phone": phone}
                for pk, name, phone in Customer.objects.order_by("name").values_list(
                    "pk", "name", "phone"
                )[:300]
            ],
            "brand_catalogue": brand_catalogue(),
        },
    )


@login_required
def intake_detail(request, pk):
    asset = get_object_or_404(
        Asset.objects.select_related("customer", "storage_slot"), pk=pk
    )
    ai_mode = request.GET.get("ai") == "1" or request.POST.get("ai_mode") == "1"

    if request.method == "POST" and "upload_stage" in request.POST:
        stage = request.POST.get("upload_stage", MediaFile.Stage.BEFORE)
        capture_angle = request.POST.get("capture_angle", "").strip()
        valid_angles = {value for value, _label in MediaFile.CaptureAngle.choices}
        if capture_angle not in valid_angles:
            capture_angle = ""
        saved, upload_errors = store_uploads(
            asset=asset,
            files=request.FILES.getlist("photos"),
            stage=stage,
            capture_angle=capture_angle,
            uploaded_by=request.user,
        )
        for error in upload_errors:
            messages.error(request, error)
        if saved:
            messages.success(request, _("Files uploaded successfully."))
        if ai_mode:
            detail_url = reverse("asset_intake:detail", args=[asset.pk])
            return redirect(f"{detail_url}?ai=1#ai-photo-upload")
        return redirect("asset_intake:detail", pk=asset.pk)

    if request.method == "POST" and "status" in request.POST:
        new_status = request.POST["status"]
        if new_status not in Asset.Status.values:
            messages.error(request, _("Invalid status."))
        elif new_status == Asset.Status.RETURNED:
            # ສົ່ງມອບເປັນຈຸດຕັດເລື່ອງເງິນ — ຕ້ອງຜ່ານ gate ດຽວກັບໜ້າ POS ສະເໝີ
            from pos.services import hand_over_asset_from_intake

            try:
                hand_over_asset_from_intake(
                    asset=asset,
                    user=request.user,
                    received_to=request.POST.get("received_to", "").strip(),
                )
            except DjangoValidationError as exc:
                for message in exc.messages:
                    messages.error(request, message)
            else:
                messages.success(request, _("Item handed over to the customer."))
        else:
            asset.status = new_status
            asset.save(update_fields=["status", "updated_at"])
            messages.success(request, _("Status updated successfully."))
        return redirect("asset_intake:detail", pk=asset.pk)

    if request.method == "POST" and "assigned_to" in request.POST:
        assigned_id = request.POST.get("assigned_to") or None
        asset.assigned_to_id = assigned_id
        asset.save(update_fields=["assigned_to", "updated_at"])
        messages.success(request, _("Work assigned to the technician successfully."))
        return redirect("asset_intake:detail", pk=asset.pk)

    checklist_items = ChecklistItem.objects.filter(is_active=True)
    latest_assessment = asset.assessments.prefetch_related(
        "items__checklist_item"
    ).first()
    latest_completed_assessment = asset.assessments.prefetch_related(
        "items__checklist_item"
    ).filter(status=Assessment.Status.DONE).first()

    assessment_items_map = {}
    if latest_assessment:
        assessment_items_map = {
            item.checklist_item_id: item for item in latest_assessment.items.all()
        }

    checklist_status = []
    for item in checklist_items:
        a_item = assessment_items_map.get(item.id)
        if a_item:
            percentage = int((a_item.score / item.max_score) * 100) if item.max_score else 0
            if percentage >= 90:
                badge_text = _("Like new")
                badge_class = "bg-ai-cyan/10 text-ai-cyan"
            elif percentage >= 75:
                badge_text = _("Minor scuffs")
                badge_class = "bg-secondary-fixed/20 text-secondary-fixed"
            else:
                badge_text = _("Worn")
                badge_class = "bg-status-error/10 text-status-error"

            checklist_status.append({
                "name": _(CHECKLIST_LABELS.get(item.name, item.name)),
                "score": f"{a_item.score:.0f}",
                "max_score": item.max_score,
                "percentage": percentage,
                "badge_text": badge_text,
                "badge_class": badge_class,
                "note": a_item.note,
                "is_pending": False,
            })
        else:
            checklist_status.append({
                "name": _(CHECKLIST_LABELS.get(item.name, item.name)),
                "score": "--",
                "max_score": item.max_score,
                "percentage": 0,
                "badge_text": _("Pending"),
                "badge_class": "bg-white/5 text-outline",
                "note": "",
                "is_pending": True,
            })

    status_labels = {
        Asset.Status.RECEIVED: _("Received"),
        Asset.Status.CLEANING: _("Cleaning"),
        Asset.Status.REPAIRING: _("Repairing"),
        Asset.Status.READY: _("Ready for pickup"),
        Asset.Status.RETURNED: _("Completed"),
    }
    asset.localized_status = status_labels.get(asset.status, asset.status)

    # ບໍລິການທີ່ຕິດກັບ order ນີ້ — ຖ້າບໍ່ມີ order (ຮັບເຄື່ອງຜ່ານໜ້າ AI Grading ໂດຍກົງ)
    # ຫຼືມີບໍລິການ AI Condition Report / ຮັບຊື້ເກີບມືສອງ ຢູ່ນຳ ຫຼືເຄີຍ run assessment ໄປແລ້ວ
    # (ບໍ່ຢາກເຊື່ອງຜົນທີ່ AI ສ້າງໄວ້ແລ້ວ) ໃຫ້ສະແດງ block checklist ສະພາບ.
    # checklist ນີ້ແມ່ນໂຄງລ່າງຮ່ວມ — ໃຊ້ຮ່ວມກັນທັງ 2 ບໍລິການ (ຄວາມສະອາດ ສຳລັບຊັກເກີບ,
    # ຄວາມແທ້/ອຸປະກອນຄົບຖ້ວນ ສຳລັບປະເມີນລາຄາຮັບຊື້) ຈຶ່ງບໍ່ຕ້ອງແຍກຕາມບໍລິການ.
    from pos.models import ServiceType

    order_items_with_service = list(
        asset.order_items.select_related("service_type").exclude(service_type__isnull=True)
    )
    service_names = {item.service_type.name for item in order_items_with_service}
    has_buyback_service = any(
        item.service_type.category == ServiceType.Category.BUYBACK
        for item in order_items_with_service
    )
    show_ai_grading = (
        ai_mode
        or not order_items_with_service
        or AI_GRADING_SERVICE_NAME in service_names
        or has_buyback_service
        or latest_assessment is not None
        or asset.valuations.exists()
    )
    # ຜົນການປະເມີນລາຄາຮັບຊື້ (panel ຄໍລຳຂວາ) ແຍກອອກຕ່າງຫາກ — ສະແດງສະເພາະອໍເດີທີ່ມີ
    # ບໍລິການ "ຮັບຊື້ເກີບມືສອງ" ແທ້ໆ ຫຼືເຄີຍປະເມີນລາຄາໄວ້ແລ້ວ (ຮັກສາຂໍ້ມູນເກົ່າກ່ອນຈະແຍກ category ນີ້)
    show_buyback = has_buyback_service or asset.valuations.exists()
    care_price_recommendation = None
    if not show_buyback:
        care_price_recommendation = build_care_price_recommendation(
            latest_completed_assessment
        )
    work_services = [
        item for item in order_items_with_service
        if item.service_type.name != AI_GRADING_SERVICE_NAME
    ]

    # ສະແດງສະເພາະຂັ້ນທີ່ຄູ່ນີ້ຈະຜ່ານແທ້ໆ — ຄູ່ທີ່ມາຊັກຢ່າງດຽວບໍ່ຕ້ອງເຫັນ "ກຳລັງສ້ອມແປງ"
    stage_order = asset.progress_stages()
    current_stage_index = (
        stage_order.index(asset.status) if asset.status in stage_order else 0
    )
    work_progress_stages = [
        {
            "value": stage,
            "label": status_labels.get(stage, stage),
            "state": (
                "done" if i < current_stage_index
                else "current" if i == current_stage_index
                else "upcoming"
            ),
        }
        for i, stage in enumerate(stage_order)
    ]

    demand_labels = {
        "High Demand": _("High demand"),
        "Normal Demand": _("Normal demand"),
        "Low Demand": _("Low demand"),
    }
    valuations = list(asset.valuations.all()[:5])
    for valuation in valuations:
        # ບໍ່ຕົກລົງມາເປັນ "High Demand" ອີກຕໍ່ໄປ — ການບອກວ່າຄວາມຕ້ອງການສູງ
        # ທັງທີ່ AI ບໍ່ໄດ້ບອກ ຈະດັນໃຫ້ຮ້ານຮັບຊື້ໃນລາຄາແພງເກີນຄວາມຈິງ
        valuation.localized_demand = demand_labels.get(
            valuation.demand_level, valuation.demand_level
        )

    before_media = list(
        asset.media_files.filter(stage=MediaFile.Stage.BEFORE)
    )
    after_media = list(
        asset.media_files.filter(stage=MediaFile.Stage.AFTER)
    )
    captured_by_angle = {}
    for media in before_media:
        if media.media_type == MediaFile.MediaType.IMAGE and media.capture_angle:
            captured_by_angle.setdefault(media.capture_angle, media)

    buyback_photo_checklist = []
    required_buyback_angles = []
    for angle, label, help_text, required in BUYBACK_PHOTO_REQUIREMENTS:
        if required:
            required_buyback_angles.append(angle)
        buyback_photo_checklist.append(
            {
                "angle": angle,
                "label": _(label),
                "help_text": _(help_text),
                "required": required,
                "media": captured_by_angle.get(angle),
            }
        )
    captured_required_count = sum(
        1 for angle in required_buyback_angles if angle in captured_by_angle
    )
    buyback_photo_complete = (
        captured_required_count == len(required_buyback_angles)
    )
    valuation_ready = (
        (not has_buyback_service or buyback_photo_complete)
        and asset.assessments.filter(status="done").exists()
    )

    context = {
        "active_nav": "intake",
        "asset": asset,
        "before_media": before_media,
        "after_media": after_media,
        "assessments": asset.assessments.all()[:5],
        "latest_assessment": latest_assessment,
        "checklist_status": checklist_status,
        "show_ai_grading": show_ai_grading,
        "show_buyback": show_buyback,
        "care_price_recommendation": care_price_recommendation,
        "buyback_photo_checklist": buyback_photo_checklist,
        "buyback_required_photo_count": len(required_buyback_angles),
        "buyback_captured_required_count": captured_required_count,
        "buyback_photo_complete": buyback_photo_complete,
        "valuation_ready": valuation_ready,
        "has_buyback_service": has_buyback_service,
        "ai_mode": ai_mode,
        "work_services": work_services,
        "work_progress_stages": work_progress_stages,
        "valuations": valuations,
        "promo_contents": asset.promo_contents.all()[:5],
        "status_choices": [
            (value, status_labels.get(value, label))
            for value, label in Asset.Status.choices
        ],
        "service_status_choices": [
            (AssetService.Status.PENDING, _("Waiting")),
            (AssetService.Status.IN_PROGRESS, _("In progress")),
            (AssetService.Status.DONE, _("Done")),
            (AssetService.Status.SKIPPED, _("Skipped")),
        ],
        "wa_link": build_wa_link(asset),
        "portal_url": absolute_url(asset.get_portal_url(), request),
        "technicians": get_user_model()
        .objects.filter(staff_profile__is_active=True)
        .select_related("staff_profile"),
    }
    return render(request, "asset_intake/intake_detail.html", context)


def _ticket_context(asset, request, **extra):
    """context ຮ່ວມຂອງໃບນັດຮັບເຄື່ອງ — QR ຊີ້ໄປໜ້າຕິດຕາມສະຖານະຂອງລູກຄ້າ"""
    portal_url = absolute_url(asset.get_portal_url(), request)
    return {
        "asset": asset,
        "portal_url": portal_url,
        "portal_qr": qr_data_uri(portal_url),
        "lookup_url": absolute_url(reverse("digital_member:lookup"), request),
        **extra,
    }


@login_required
def ticket_view(request, pk):
    asset = get_object_or_404(Asset.objects.select_related("customer"), pk=pk)
    return render(
        request, "asset_intake/pickup_ticket.html", _ticket_context(asset, request)
    )


@login_required
def ticket_pdf(request, pk):
    asset = get_object_or_404(Asset.objects.select_related("customer"), pk=pk)
    from core.pdf_fonts import pdf_font_context, pdf_response

    html = render_to_string(
        "asset_intake/pickup_ticket.html",
        _ticket_context(asset, request, for_pdf=True, **pdf_font_context()),
    )
    return pdf_response(html, f"{asset.ticket_number}.pdf")


@login_required
def tag_label(request, pk):
    """ປ້າຍແທັກ QR ນ້ອຍ ສຳລັບພິມຫ້ອຍຕິດເກີບ — ສະແກນແລ້ວເປີດໜ້າ portal ລູກຄ້າ (ຢືນຢັນດ້ວຍເບີໂທ)"""
    asset = get_object_or_404(Asset.objects.select_related("customer"), pk=pk)
    portal_url = absolute_url(asset.get_portal_url(), request)
    return render(
        request,
        "asset_intake/tag_label.html",
        {"asset": asset, "tag_qr": qr_data_uri(portal_url, box_size=12)},
    )


@login_required
def asset_edit(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    if request.method == "POST":
        asset.brand = request.POST.get("brand", "").strip()
        asset.model_name = request.POST.get("model_name", "").strip()
        asset.color = request.POST.get("color", "").strip()
        asset.size = request.POST.get("size", "").strip()
        new_status = request.POST.get("status", asset.status)
        if new_status in Asset.Status.values:
            asset.status = new_status
        asset.condition_note = request.POST.get("condition_note", "").strip()
        asset.save()
    return redirect("asset_intake:detail", pk=pk)


@login_required
def asset_delete(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    if request.method == "POST":
        asset.delete()
    return redirect("asset_intake:list")


@login_required
def social_image(request, pk):
    """ສ້າງຮູບ Before/After ຂະໜາດ 1080x1080 ສຳລັບໂພສ Facebook/Instagram"""
    asset = get_object_or_404(Asset, pk=pk)
    before = asset.media_files.filter(
        stage=MediaFile.Stage.BEFORE, media_type=MediaFile.MediaType.IMAGE
    ).first()
    after = asset.media_files.filter(
        stage=MediaFile.Stage.AFTER, media_type=MediaFile.MediaType.IMAGE
    ).first()
    if not before or not after:
        messages.error(request, "ຕ້ອງມີຮູບກ່ອນຊັກ ແລະ ຫຼັງຊັກ ຢ່າງໜ້ອຍຢ່າງລະ 1 ຮູບກ່ອນ")
        return redirect("asset_intake:detail", pk=asset.pk)

    from .social import compose_before_after

    # ຮູບທີ່ອັບຄ້າງ (ເນັດຫຼຸດກາງທາງ) ຜ່ານການກວດຕອນອັບໂຫຼດໄດ້ ເພາະຫົວໄຟລ໌ຍັງດີ
    # ແຕ່ PIL ເປີດບໍ່ໄດ້ຕອນມາປະກອບຮູບ — ຢ່າໃຫ້ໜ້າ 500 ໃສ່ພະນັກງານ
    try:
        png_bytes = compose_before_after(
            before.file.path,
            after.file.path,
            caption=f"{asset.brand} {asset.model_name}".strip(),
        )
    except (OSError, ValueError):
        messages.error(
            request,
            _(
                "One of the photos is damaged and cannot be opened. "
                "Please upload the before and after photos again."
            ),
        )
        return redirect("asset_intake:detail", pk=asset.pk)

    response = HttpResponse(png_bytes, content_type="image/png")
    response["Content-Disposition"] = (
        f'attachment; filename="hugkerb-{asset.ticket_number}-before-after.png"'
    )
    return response


@login_required
def kanban_board(request):
    """ກະດານຕິດຕາມການເຮັດວຽກ — card ໜຶ່ງ = ວຽກບໍລິການໜຶ່ງອັນ (ບໍ່ແມ່ນຄູ່ເກີບ)

    ຄູ່ທີ່ມາຊັກຢ່າງດຽວຈະມີ card ດຽວໃນແຖວ "ຊັກ",
    ຄູ່ທີ່ເຮັດທັງຊັກ ແລະ ສ້ອມ ຈະມີ 2 card ຢູ່ຄົນລະແຖວ ຍ້າຍເປັນອິດສະຫຼະຕໍ່ກັນ.
    ສະຖານະຂອງຄູ່ເກີບຄິດໄລ່ມາຈາກ card ເຫຼົ່ານີ້ (ເບິ່ງ Asset.compute_status)
    """
    from pos.models import ServiceType

    stages = [
        {"id": AssetService.Status.PENDING, "name": _("Waiting")},
        {"id": AssetService.Status.IN_PROGRESS, "name": _("In progress")},
        {"id": AssetService.Status.DONE, "name": _("Done")},
    ]

    # ບໍ່ເອົາຄູ່ທີ່ສົ່ງມອບແລ້ວ ແລະວຽກທີ່ຖືກຂ້າມ
    services = (
        AssetService.objects.select_related(
            "asset", "asset__customer", "asset__storage_slot", "assigned_to"
        )
        .exclude(asset__status=Asset.Status.RETURNED)
        .exclude(status=AssetService.Status.SKIPPED)
    )

    # ຕົວກັ່ນຕອງແຖວວຽກ — ຊ່າງຊັກເບິ່ງແຕ່ວຽກຊັກໄດ້
    work_types = [
        {"id": value, "name": label} for value, label in ServiceType.WorkType.choices
    ]
    active_work_type = request.GET.get("work_type", "")
    if active_work_type not in ServiceType.WorkType.values:
        active_work_type = ""

    # ຈັດເປັນ swimlane (ແຖວ = ປະເພດວຽກ) × ຖັນ (ສະຖານະ)
    grouped = {}
    for service in services:
        if active_work_type and service.work_type != active_work_type:
            continue
        grouped.setdefault(service.work_type, {}).setdefault(service.status, []).append(
            service
        )

    lanes = []
    for work_type in work_types:
        by_status = grouped.get(work_type["id"])
        if not by_status:
            continue
        lanes.append(
            {
                "id": work_type["id"],
                "name": work_type["name"],
                "total": sum(len(items) for items in by_status.values()),
                "columns": [
                    {
                        "id": stage["id"],
                        "name": stage["name"],
                        "items": by_status.get(stage["id"], []),
                    }
                    for stage in stages
                ],
            }
        )

    return render(
        request,
        "asset_intake/kanban_board.html",
        {
            "active_nav": "kanban",
            "stages": stages,
            "lanes": lanes,
            "work_types": work_types,
            "active_work_type": active_work_type,
        },
    )


@login_required
def kanban_update_status(request):
    import json
    from django.http import JsonResponse
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            service_id = data.get("service_id")
            new_status = data.get("status")

            service = AssetService.objects.select_related(
                "asset", "asset__customer"
            ).get(pk=service_id)
            asset = service.asset
            if new_status in AssetService.Status.values:
                service.status = new_status
                # ບັນທຶກວຽກ → ໂມເດລຈະ rollup ສະຖານະຄູ່ເກີບໃຫ້ເອງ
                # (ແລະ Asset.save ຈະແຈ້ງເຕືອນລູກຄ້າ ຖ້າສະຖານະຄູ່ປ່ຽນຈິງ)
                service.save(update_fields=["status"])
                asset.refresh_from_db()
                # ຜົນການແຈ້ງເຕືອນທີ່ຫາກໍສົ່ງ (Telegram/WhatsApp) — ໃຫ້ໜ້າ board ໂຊ toast
                from notifications.models import NotificationLog

                notifications = list(
                    NotificationLog.objects.filter(
                        asset=asset,
                        created_at__gte=timezone.now() - timedelta(seconds=10),
                    ).values("channel", "is_sent")
                )
                return JsonResponse(
                    {
                        "success": True,
                        "status": asset.status,
                        "ticket": asset.ticket_number,
                        "customer": asset.customer.name,
                        "notifications": notifications,
                        # ລິ້ງ wa.me ສຳຮອງ — ໃຫ້ພະນັກງານກົດສົ່ງເອງ ຖ້າຍັງບໍ່ໄດ້ຕັ້ງ Cloud API
                        "wa_link": build_wa_link(asset),
                    }
                )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
    return JsonResponse({"success": False, "error": "Invalid request"}, status=400)


@login_required
def service_update(request):
    """ປ່ຽນສະຖານະວຽກບໍລິການໜຶ່ງອັນ ຈາກໜ້າລາຍລະອຽດເກີບ (POST: service_id, status)"""
    if request.method != "POST":
        return redirect("asset_intake:kanban")

    service = get_object_or_404(AssetService, pk=request.POST.get("service_id"))
    new_status = request.POST.get("status")
    if new_status in AssetService.Status.values:
        service.status = new_status
        service.save(update_fields=["status"])
        messages.success(
            request, _("Updated:") + f" {service.label} → {service.get_status_display()}"
        )

    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("asset_intake:detail", pk=service.asset_id)


@login_required
def storage_map(request):
    """ຜັງບ່ອນເກັບເກີບ — ຄືຜັງບ່ອນນັ່ງໂຮງໜັງ (ຂຽວ=ຫວ່າງ, ແດງ=ເຕັມ)
    ໂໝດເລືອກບ່ອນ: ?assign=<asset_pk> → ກົດຊ່ອງຫວ່າງເພື່ອມອບບ່ອນເກັບໃຫ້ asset ນັ້ນ"""
    assign_asset = None
    assign_pk = request.GET.get("assign")
    if assign_pk:
        assign_asset = (
            Asset.objects.select_related("customer")
            .filter(pk=assign_pk)
            .exclude(status=Asset.Status.RETURNED)
            .first()
        )

    slots = StorageSlot.objects.filter(is_active=True).select_related(
        "asset", "asset__customer"
    )

    total = occupied = 0
    for slot in slots:
        total += 1
        if hasattr(slot, "asset"):
            occupied += 1

    zone_list = build_zone_rows(
        slots,
        lambda slot: {"slot": slot, "asset": getattr(slot, "asset", None)},
    )

    return render(
        request,
        "asset_intake/storage_map.html",
        {
            "active_nav": "storage",
            "zones": zone_list,
            "assign_asset": assign_asset,
            "total_slots": total,
            "occupied_slots": occupied,
            "free_slots": total - occupied,
        },
    )


@login_required
def storage_assign(request):
    """ມອບບ່ອນເກັບໃຫ້ asset (POST: asset_id, slot_id)"""
    if request.method != "POST":
        return redirect("asset_intake:storage")

    asset = get_object_or_404(Asset, pk=request.POST.get("asset_id"))
    slot = get_object_or_404(
        StorageSlot, pk=request.POST.get("slot_id"), is_active=True
    )

    if asset.status == Asset.Status.RETURNED:
        messages.error(request, _("This item was already delivered — no storage slot needed."))
        return redirect("asset_intake:detail", pk=asset.pk)

    if hasattr(slot, "asset") and slot.asset.pk != asset.pk:
        messages.error(request, _("That slot is already occupied. Please pick a green one."))
        return redirect(f"{reverse('asset_intake:storage')}?assign={asset.pk}")

    asset.storage_slot = slot
    asset.save(update_fields=["storage_slot", "updated_at"])
    messages.success(request, _("Storage slot saved:") + f" {slot.code}")
    return redirect("asset_intake:detail", pk=asset.pk)


@login_required
def storage_release(request):
    """ຄືນບ່ອນເກັບ (POST: asset_id)"""
    if request.method != "POST":
        return redirect("asset_intake:storage")

    asset = get_object_or_404(Asset, pk=request.POST.get("asset_id"))
    asset.storage_slot = None
    asset.save(update_fields=["storage_slot", "updated_at"])
    messages.success(request, _("Storage slot released."))
    return redirect("asset_intake:detail", pk=asset.pk)


# ══════════ ຈັດການຍີ່ຫໍ້ ແລະ ລຸ້ນເກີບ (Scope 2.3) ══════════


def brand_catalogue():
    """ຍີ່ຫໍ້ທີ່ເປີດໃຊ້ພ້ອມລຸ້ນຂອງມັນ — ໃຊ້ຮ່ວມກັນລະຫວ່າງໜ້າຮັບເຄື່ອງ ແລະ ໜ້າ POS

    ຄືນເປັນ dict {ຊື່ຍີ່ຫໍ້: [ຊື່ລຸ້ນ, ...]} ເພື່ອຝັງເປັນ JSON ໃນໜ້າ
    ແລ້ວໃຫ້ຝັ່ງ browser ກັ່ນຕອງເອງ — ບໍ່ຕ້ອງຍິງ request ທຸກຄັ້ງທີ່ປ່ຽນຍີ່ຫໍ້
    (ຮ້ານມີຍີ່ຫໍ້ບໍ່ຮອດຮ້ອຍ ຂໍ້ມູນຈຶ່ງນ້ອຍພໍທີ່ຈະສົ່ງໄປພ້ອມໜ້າໄດ້)
    """
    catalogue = {}
    for brand in Brand.objects.filter(is_active=True).prefetch_related("shoe_models"):
        catalogue[brand.name] = [
            model.name for model in brand.shoe_models.all() if model.is_active
        ]
    return catalogue


@login_required
def brand_list(request):
    brands = Brand.objects.prefetch_related("shoe_models").order_by(
        "sort_order", "name"
    )
    return render(
        request,
        "asset_intake/brand_list.html",
        {"active_nav": "brands", "brands": brands},
    )


@login_required
@require_POST
def brand_create(request):
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, _("Enter a brand name."))
    elif Brand.objects.filter(name__iexact=name).exists():
        messages.error(request, _("That brand already exists."))
    else:
        Brand.objects.create(
            name=name,
            sort_order=int(request.POST.get("sort_order") or 0),
        )
        messages.success(request, _("Brand added:") + f" {name}")
    return redirect("asset_intake:brands")


@login_required
@require_POST
def brand_update(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, _("Enter a brand name."))
    elif Brand.objects.filter(name__iexact=name).exclude(pk=brand.pk).exists():
        messages.error(request, _("That brand already exists."))
    else:
        brand.name = name
        brand.sort_order = int(request.POST.get("sort_order") or 0)
        brand.is_active = request.POST.get("is_active") == "on"
        brand.save()
        messages.success(request, _("Brand updated."))
    return redirect("asset_intake:brands")


@login_required
@require_POST
def brand_delete(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    # ຄູ່ເກີບເກັບຍີ່ຫໍ້ເປັນຂໍ້ຄວາມ ບໍ່ແມ່ນ FK — ລຶບຍີ່ຫໍ້ຈຶ່ງບໍ່ກະທົບປະຫວັດເກົ່າ
    # ແຕ່ຍັງເຕືອນໄວ້ ເພື່ອບໍ່ໃຫ້ພະນັກງານເຂົ້າໃຈວ່າປະຫວັດຫາຍໄປນຳ
    used = Asset.objects.filter(brand__iexact=brand.name).count()
    brand.delete()
    if used:
        messages.success(
            request,
            _("Brand removed from the list. %(count)d past item(s) keep their record.")
            % {"count": used},
        )
    else:
        messages.success(request, _("Brand removed."))
    return redirect("asset_intake:brands")


@login_required
@require_POST
def shoe_model_create(request, brand_pk):
    brand = get_object_or_404(Brand, pk=brand_pk)
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, _("Enter a model name."))
    elif brand.shoe_models.filter(name__iexact=name).exists():
        messages.error(request, _("That model already exists for this brand."))
    else:
        ShoeModel.objects.create(brand=brand, name=name)
        messages.success(request, _("Model added:") + f" {brand.name} {name}")
    return redirect("asset_intake:brands")


@login_required
@require_POST
def shoe_model_delete(request, pk):
    model = get_object_or_404(ShoeModel, pk=pk)
    model.delete()
    messages.success(request, _("Model removed."))
    return redirect("asset_intake:brands")
