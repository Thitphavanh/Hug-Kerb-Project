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
from xhtml2pdf import pisa

from ai_mart_grading.models import ChecklistItem
from crm.models import Customer
from media_backup.models import MediaFile
from notifications.services import build_wa_link

from .forms import IntakeForm
from .models import Asset
from .utils import absolute_url, qr_data_uri


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
    asset = get_object_or_404(Asset.objects.select_related("customer"), pk=pk)

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
        messages.success(request, "ອັບໂຫຼດໄຟລ໌ສຳເລັດ")
        return redirect("asset_intake:detail", pk=asset.pk)

    if request.method == "POST" and "status" in request.POST:
        new_status = request.POST["status"]
        if new_status in Asset.Status.values:
            asset.status = new_status
            asset.save(update_fields=["status", "updated_at"])
            messages.success(request, "ອັບເດດສະຖານະແລ້ວ")
        else:
            messages.error(request, "ສະຖານະບໍ່ຖືກຕ້ອງ")
        return redirect("asset_intake:detail", pk=asset.pk)

    if request.method == "POST" and "assigned_to" in request.POST:
        assigned_id = request.POST.get("assigned_to") or None
        asset.assigned_to_id = assigned_id
        asset.save(update_fields=["assigned_to", "updated_at"])
        messages.success(request, "ມອບວຽກໃຫ້ຊ່າງແລ້ວ")
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
                badge_text = "Like New"
                badge_class = "bg-ai-cyan/10 text-ai-cyan"
            elif percentage >= 75:
                badge_text = "Minor Scuffs"
                badge_class = "bg-secondary-fixed/20 text-secondary-fixed"
            else:
                badge_text = "Worn"
                badge_class = "bg-status-error/10 text-status-error"

            checklist_status.append({
                "name": item.name,
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
                "name": item.name,
                "score": "--",
                "max_score": item.max_score,
                "percentage": 0,
                "badge_text": "Pending",
                "badge_class": "bg-white/5 text-outline",
                "note": "",
                "is_pending": True,
            })

    context = {
        "active_nav": "intake",
        "asset": asset,
        "before_media": asset.media_files.filter(stage=MediaFile.Stage.BEFORE),
        "after_media": asset.media_files.filter(stage=MediaFile.Stage.AFTER),
        "assessments": asset.assessments.all()[:5],
        "latest_assessment": latest_assessment,
        "checklist_status": checklist_status,
        "valuations": asset.valuations.all()[:5],
        "promo_contents": asset.promo_contents.all()[:5],
        "status_choices": Asset.Status.choices,
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
    assets = Asset.objects.select_related("customer", "assigned_to").filter(
        ~Q(status=Asset.Status.RETURNED) | Q(updated_at__gte=week_ago)
    )

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
