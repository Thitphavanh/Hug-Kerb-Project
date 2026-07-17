from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from ai_mart_grading.models import ChecklistItem
from crm.models import Customer
from media_backup.models import MediaFile
from notifications.services import build_wa_link

from .forms import IntakeForm
from .models import Asset, StorageSlot
from .utils import absolute_url, qr_data_uri


CHECKLIST_LABELS = {
    "ຮອຍເປື້ອນ/ຄວາມສະອາດຂອງໜ້າເກີບ": "Upper cleanliness and stains",
    "Laces condition": "Laces condition",
    "ຮອຍຈີກ/ຮອຍແຕກຂອງວັດສະດຸໜ້າເກີບ": "Upper material tears or cracks",
    "Upper / body condition": "Upper / body condition",
    "ສີຊີດຈາງ/ປ່ຽນສີ": "Fading or discoloration",
    "Sole condition": "Sole condition",
    "ການສຶກຫຼໍ່ຂອງພື້ນນອກ (Outsole)": "Outsole wear",
    "Insole condition": "Insole condition",
    "Midsole ແຕກ/ຍຸບ/ເສື່ອມ": "Midsole cracks, compression, or deterioration",
    "Color condition": "Color condition",
    "ພື້ນເຫຼືອງ (Oxidation)": "Sole yellowing (oxidation)",
    "ສະພາບພື້ນໃນ ແລະ ກິ່ນ": "Insole condition and odor",
    "ສາຍເກີບຄົບ ແລະ ສະພາບດີ": "Laces completeness and condition",
    "ກ່ອງ/ອຸປະກອນເສີມຄົບຖ້ວນ": "Box and accessories completeness",
    "ການກວດຄວາມແທ້ເບື້ອງຕົ້ນ (Authenticity)": "Preliminary authenticity check",
}

# ບໍລິການທີ່ໃຊ້ AI Grading checklist + ລາຄາຂາຍຕໍ່ — ບໍລິການອື່ນ (ຊັກ/ສ້ອມ/ສະປາ) ບໍ່ຕ້ອງການ 2 ອັນນີ້
AI_GRADING_SERVICE_NAME = "AI Condition Report"


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
            customer, created = Customer.objects.get_or_create(
                phone=data["customer_phone"],
                defaults={"name": data["customer_name"]},
            )
            if not created and customer.name != data["customer_name"]:
                customer.name = data["customer_name"]
                customer.save(update_fields=["name"])

            asset = Asset.objects.create(
                customer=customer,
                brand=data["brand"],
                model_name=data["model_name"],
                color=data["color"],
                size=data["size"],
                condition_note=data["condition_note"],
                pickup_date=data["pickup_date"],
            )
            for f in request.FILES.getlist("photos"):
                MediaFile.objects.create(
                    asset=asset,
                    file=f,
                    stage=MediaFile.Stage.BEFORE,
                    media_type=MediaFile.MediaType.IMAGE,
                )

            messages.success(
                request, f"ຮັບເຄື່ອງສຳເລັດ — ເລກໃບຮັບ {asset.ticket_number}"
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
            "customers": Customer.objects.order_by("name")[:200],
        },
    )


@login_required
def intake_detail(request, pk):
    asset = get_object_or_404(
        Asset.objects.select_related("customer", "storage_slot"), pk=pk
    )

    if request.method == "POST" and "upload_stage" in request.POST:
        stage = request.POST.get("upload_stage", MediaFile.Stage.BEFORE)
        for f in request.FILES.getlist("photos"):
            is_video = (f.content_type or "").startswith("video")
            MediaFile.objects.create(
                asset=asset,
                file=f,
                stage=stage,
                media_type=(
                    MediaFile.MediaType.VIDEO if is_video else MediaFile.MediaType.IMAGE
                ),
            )
        messages.success(request, _("Files uploaded successfully."))
        return redirect("asset_intake:detail", pk=asset.pk)

    if request.method == "POST" and "status" in request.POST:
        new_status = request.POST["status"]
        if new_status in Asset.Status.values:
            asset.status = new_status
            asset.save(update_fields=["status", "updated_at"])
            messages.success(request, _("Status updated successfully."))
        else:
            messages.error(request, _("Invalid status."))
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
    # ຫຼືມີບໍລິການ AI Condition Report ຢູ່ນຳ ຫຼືເຄີຍ run assessment/valuation ໄປແລ້ວ
    # (ບໍ່ຢາກເຊື່ອງຜົນທີ່ AI ສ້າງໄວ້ແລ້ວ) ໃຫ້ສະແດງ block AI checklist + ລາຄາຂາຍຕໍ່ຄືເກົ່າ.
    # ຖ້າມີແຕ່ບໍລິການອື່ນ (ຊັກ/ສ້ອມ/ສະປາ) ແລະ ບໍ່ເຄີຍປະເມີນ ໃຫ້ສະແດງ block ຄວາມຄືບໜ້າວຽກແທນ.
    order_items_with_service = list(
        asset.order_items.select_related("service_type").exclude(service_type__isnull=True)
    )
    service_names = {item.service_type.name for item in order_items_with_service}
    show_ai_grading = (
        not order_items_with_service
        or AI_GRADING_SERVICE_NAME in service_names
        or latest_assessment is not None
        or asset.valuations.exists()
    )
    work_services = [
        item for item in order_items_with_service
        if item.service_type.name != AI_GRADING_SERVICE_NAME
    ]

    stage_order = [
        Asset.Status.RECEIVED,
        Asset.Status.CLEANING,
        Asset.Status.REPAIRING,
        Asset.Status.READY,
        Asset.Status.RETURNED,
    ]
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
        demand_level = (valuation.raw_response or {}).get(
            "demand_level", "High Demand"
        )
        valuation.localized_demand = demand_labels.get(demand_level, demand_level)

    context = {
        "active_nav": "intake",
        "asset": asset,
        "before_media": asset.media_files.filter(stage=MediaFile.Stage.BEFORE),
        "after_media": asset.media_files.filter(stage=MediaFile.Stage.AFTER),
        "assessments": asset.assessments.all()[:5],
        "latest_assessment": latest_assessment,
        "checklist_status": checklist_status,
        "show_ai_grading": show_ai_grading,
        "work_services": work_services,
        "work_progress_stages": work_progress_stages,
        "valuations": valuations,
        "promo_contents": asset.promo_contents.all()[:5],
        "status_choices": [
            (value, status_labels.get(value, label))
            for value, label in Asset.Status.choices
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

    png_bytes = compose_before_after(
        before.file.path,
        after.file.path,
        caption=f"{asset.brand} {asset.model_name}".strip(),
    )
    response = HttpResponse(png_bytes, content_type="image/png")
    response["Content-Disposition"] = (
        f'attachment; filename="hugkerb-{asset.ticket_number}-before-after.png"'
    )
    return response


@login_required
def kanban_board(request):
    # ວຽກຄ້າງທັງໝົດ + ວຽກທີ່ສົ່ງມອບພາຍໃນ 7 ວັນຫຼ້າສຸດ (ຖັນ Completed ບໍ່ຮົກ)
    week_ago = timezone.now() - timedelta(days=7)
    assets = Asset.objects.select_related(
        "customer", "assigned_to", "storage_slot"
    ).filter(~Q(status=Asset.Status.RETURNED) | Q(updated_at__gte=week_ago))

    stages = [
        {"id": "received", "name": _("Intake")},
        {"id": "cleaning", "name": _("Cleaning")},
        {"id": "repairing", "name": _("Repairing")},
        {"id": "ready", "name": _("Ready for pickup")},
        {"id": "returned", "name": _("Completed"), "hint": _("Last 7 days")},
    ]
    
    return render(
        request,
        "asset_intake/kanban_board.html",
        {
            "active_nav": "kanban",
            "assets": assets,
            "stages": stages,
        }
    )


@login_required
def kanban_update_status(request):
    import json
    from django.http import JsonResponse
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            asset_id = data.get("asset_id")
            new_status = data.get("status")
            
            asset = Asset.objects.get(pk=asset_id)
            if new_status in [choice[0] for choice in Asset.Status.choices]:
                asset.status = new_status
                asset.save(update_fields=["status", "updated_at"])
                return JsonResponse({"success": True, "status": asset.status})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
    return JsonResponse({"success": False, "error": "Invalid request"}, status=400)


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

    zones = {}
    total = occupied = 0
    for slot in slots:
        occupant = slot.asset if hasattr(slot, "asset") else None
        total += 1
        if occupant:
            occupied += 1
        zones.setdefault(slot.zone, {}).setdefault(slot.cabinet, []).append(
            {"slot": slot, "asset": occupant}
        )

    zone_list = [
        {
            "name": zone,
            "cabinets": [
                {"number": cab, "slots": items} for cab, items in cabinets.items()
            ],
        }
        for zone, cabinets in zones.items()
    ]

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
