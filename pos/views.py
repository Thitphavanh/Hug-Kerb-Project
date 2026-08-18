import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, gettext as _

from asset_intake.views import brand_catalogue
from inventory.models import StockMovement, Supply
from media_backup.services import intake_photo_slots
from staff.decorators import role_required
from staff.models import StaffProfile, get_role

from .models import (
    BASE_CURRENCY,
    CURRENCY_CHOICES,
    Order,
    OrderItem,
    Payment,
    ServiceType,
    generate_order_number,
)
from .scanning import open_order_for_scan, resolve_scan_code
from .services import hand_over_asset, record_payment, void_payment

manager_required = role_required(StaffProfile.Role.MANAGER)


@login_required
def customer_search(request):
    """Return a small autocomplete list for the POS customer picker."""
    from crm.models import Customer

    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse({"results": []})

    customers = (
        Customer.objects.filter(
            Q(name__icontains=query) | Q(phone__icontains=query)
        )
        .order_by("name", "phone")[:8]
    )
    return JsonResponse({
        "results": [
            {"id": customer.pk, "name": customer.name, "phone": customer.phone}
            for customer in customers
        ]
    })


@login_required
def storage_map_data(request):
    """JSON storage map ສຳລັບ modal ເລືອກບ່ອນເກັບໃນໜ້າສ້າງອໍເດີ (POS)
    ໂຄງສ້າງດຽວກັບ asset_intake:storage ແຕ່ເປັນ read-only (ຍັງບໍ່ມີ Asset ຈິງຕອນນີ້)
    """
    from asset_intake.models import StorageSlot, build_zone_rows

    slots = StorageSlot.objects.filter(is_active=True).select_related(
        "asset", "asset__customer"
    )

    total = free = 0
    for slot in slots:
        total += 1
        if getattr(slot, "asset", None) is None:
            free += 1

    def to_item(slot):
        occupant = getattr(slot, "asset", None)
        return {
            "id": slot.pk,
            "code": slot.code,
            "free": occupant is None,
            "ticket_number": occupant.ticket_number if occupant else "",
            "customer_name": occupant.customer.name if occupant else "",
            "brand_model": (
                f"{occupant.brand} {occupant.model_name}".strip() if occupant else ""
            ),
        }

    zone_list = build_zone_rows(slots, to_item)

    return JsonResponse({
        "zones": zone_list,
        "total": total,
        "free": free,
        "occupied": total - free,
    })


@login_required
def scan_lookup(request):
    """ຄົ້ນຫາຈາກຄ່າທີ່ສະແກນໄດ້ (ປ້າຍແທັກ QR, ໃບຮັບເຄື່ອງ, ເລກອໍເດີ)
    ຮັບ ?code= ເປັນ: ເລກໃບຮັບເຄື່ອງ TK-..., ເລກອໍເດີ ORD...,
    ຫຼື URL ຈາກ QR ໃນລະບົບ (/t/<token>/ ຂອງ portal, /<pk>/ ຂອງປ້າຍແທັກ)
    """
    code = request.GET.get("code", "").strip()
    if not code:
        return JsonResponse({"found": False, "error": "empty"}, status=400)

    asset, order = resolve_scan_code(code)

    if order is not None:
        # ດຶງເຄື່ອງໂຕທຳອິດຂອງອໍເດີມານຳ ເພື່ອຕື່ມຟອມລາຍການ
        first_item = order.items.select_related("asset").filter(
            asset__isnull=False
        ).first()
        asset = first_item.asset if first_item else None
        customer = order.customer
        label = order.order_number
        source = "order"
    elif asset is not None:
        customer = asset.customer
        label = asset.ticket_number
        source = "asset"
    else:
        return JsonResponse({"found": False})

    return JsonResponse({
        "found": True,
        "source": source,
        "label": label,
        "customer": {
            "id": customer.pk if customer else None,
            "name": customer.name if customer else "",
            "phone": customer.phone if customer else "",
        },
        "asset": {
            "brand": asset.brand,
            "model_name": asset.model_name,
            "color": asset.color,
            "size": asset.size,
        } if asset else None,
    })


# ------------------------------------------------------------------
# ລາຄາ ແລະ ບໍລິການ — ໃຊ້ຮ່ວມກັນລະຫວ່າງໜ້າຂາຍໜ້າຮ້ານ ແລະ ໜ້າແກ້ບິນເກົ່າ
# ------------------------------------------------------------------

# ລະຫັດສ່ວນຫຼຸດຂອງຮ້ານ: (ເປີເຊັນ, ຈຳນວນເງິນຄົງທີ່)
PROMO_CODES = {
    "KVAIPRO20": (20, 0),
    "RAINY15": (0, 15000),
    "MISSYOU25": (0, 25000),
}


def promo_discount(subtotal, code):
    """ຄິດເປັນຈຳນວນເງິນສ່ວນຫຼຸດຈາກລະຫັດ — ລະຫັດບໍ່ຖືກຕ້ອງ = ບໍ່ຫຼຸດ"""
    percent, flat = PROMO_CODES.get((code or "").strip().upper(), (0, 0))
    if percent:
        return int(Decimal(subtotal) * percent / 100)
    # ຫຼຸດແບບຈຳນວນເງິນ ຫ້າມເກີນຍອດບິນ — ບໍ່ດັ່ງນັ້ນຍອດຈະຕິດລົບ
    return min(int(flat), int(subtotal))


def build_service_groups():
    """ບໍລິການແຍກເປັນໝວດ — ໃຊ້ວາງເປັນບລັອກເລືອກໃນໜ້າຂາຍ ແລະ ໜ້າແກ້ບິນ"""
    all_services = ServiceType.objects.filter(is_active=True)
    return [
        {
            "key": ServiceType.Category.AI_ASSESSMENT,
            "title": "AI assessment",
            "services": all_services.filter(
                category=ServiceType.Category.AI_ASSESSMENT
            ),
        },
        {
            "key": ServiceType.Category.PRIMARY,
            "title": "Primary services",
            "services": all_services.filter(category=ServiceType.Category.PRIMARY),
        },
        {
            "key": ServiceType.Category.ADD_ON,
            "title": "Repair and add-on services",
            "services": all_services.filter(category=ServiceType.Category.ADD_ON),
        },
    ]



def _attach_intake_photos(request, asset, prefix):
    """ເກັບຮູບ "ກ່ອນເຮັດ" ທີ່ຖ່າຍຕອນເປີດບິນ ໃສ່ຄູ່ເກີບທີ່ຫາກໍສ້າງ (Scope 2.3)

    ຮູບກ່ອນເຮັດຄືຫຼັກຖານດຽວທີ່ຮ້ານໃຊ້ຢືນຢັນສະພາບເດີມກັບລູກຄ້າ ຖ້າມີຂໍ້ຂັດແຍ່ງ
    ຈຶ່ງຕ້ອງຖ່າຍໄດ້ຕັ້ງແຕ່ຕອນຮັບເຄື່ອງ ບໍ່ແມ່ນລໍໃຫ້ເປີດໜ້າລາຍລະອຽດກ່ອນ.

    ແຍກເປັນຊ່ອງຕາມມຸມ (ດ້ານໜ້າ, ພື້ນເກີບ, ສາຍເກີບ...) ເພື່ອໃຫ້ຮູບຖືກຈຸດ
    ແລະ AI ປະເມີນໄດ້ຖືກຕ້ອງ — ຜ່ານຕົວກວດຂະໜາດ/ຊະນິດອັນດຽວກັບໜ້າຮັບເຄື່ອງ
    """
    from media_backup.services import store_slot_uploads

    _saved, errors = store_slot_uploads(
        asset=asset,
        get_files=request.FILES.getlist,
        prefix=prefix,
        uploaded_by=request.user,
    )
    for error in errors:
        messages.error(request, error)


@login_required
def create_order(request):
    if request.method == "POST":
        next_action = request.POST.get("next_action", "invoice")
        customer_id = request.POST.get("customer_id", "").strip()
        customer_name = request.POST.get("customer_name", "").strip()
        customer_phone = request.POST.get("customer_phone", "").strip()

        if customer_name and customer_phone:
            from crm.models import Customer
            from asset_intake.models import Asset, StorageSlot

            customer = (
                Customer.objects.filter(pk=customer_id).first()
                if customer_id.isdigit()
                else None
            )
            if customer is None:
                customer, _ = Customer.objects.get_or_create(
                    phone=customer_phone,
                    defaults={"name": customer_name}
                )

            # Check if we have multiple items indexed
            indices_str = request.POST.get("item_indices")
            if indices_str:
                indices = [int(i.strip()) for i in indices_str.split(",") if i.strip().isdigit()]
            else:
                indices = []

            # Create Order
            order = Order.objects.create(
                customer=customer,
                status=Order.Status.OPEN,
                created_by=request.user,
            )
            created_assets = []

            if indices:
                # Multi-item processing
                for idx in indices:
                    brand = request.POST.get(f"brand_{idx}", "").strip()
                    model_name = request.POST.get(f"model_name_{idx}", "").strip()
                    color = request.POST.get(f"color_{idx}", "").strip()
                    size = request.POST.get(f"size_{idx}", "").strip()
                    service_id = request.POST.get(f"service_{idx}", "")
                    storage_slot_id = request.POST.get(
                        f"storage_slot_{idx}", ""
                    ).strip()

                    if brand or model_name:
                        storage_slot = None
                        if storage_slot_id.isdigit():
                            storage_slot = StorageSlot.objects.filter(
                                pk=storage_slot_id,
                                is_active=True,
                                asset__isnull=True,
                            ).first()
                            if storage_slot is None:
                                messages.warning(
                                    request,
                                    gettext(
                                        "The selected storage slot is no longer "
                                        "available. Please choose another slot."
                                    ),
                                )

                        # Create Asset
                        asset = Asset.objects.create(
                            customer=customer,
                            brand=brand,
                            model_name=model_name,
                            color=color,
                            size=size,
                            status=Asset.Status.RECEIVED,
                            storage_slot=storage_slot,
                        )
                        created_assets.append(asset)
                        _attach_intake_photos(request, asset, f"photos_{idx}")

                        # Create OrderItem
                        try:
                            service = ServiceType.objects.exclude(
                                category=ServiceType.Category.AI_ASSESSMENT
                            ).get(pk=service_id)
                            desc = f"{service.name} for {brand} {model_name}"
                            if color:
                                desc += f" ({color})"
                            OrderItem.objects.create(
                                order=order,
                                service_type=service,
                                asset=asset,
                                description=desc,
                                quantity=1,
                                unit_price=service.price
                            )
                        except ServiceType.DoesNotExist:
                            pass
            else:
                # Single fallback item
                brand = request.POST.get("brand", "").strip()
                model_name = request.POST.get("model_name", "").strip()
                color = request.POST.get("color", "").strip()
                size = request.POST.get("size", "").strip()
                service_id = request.POST.get("service", "")
                storage_slot_id = request.POST.get("storage_slot", "").strip()
                
                if brand or model_name:
                    storage_slot = None
                    if storage_slot_id.isdigit():
                        storage_slot = StorageSlot.objects.filter(
                            pk=storage_slot_id,
                            is_active=True,
                            asset__isnull=True,
                        ).first()
                        if storage_slot is None:
                            messages.warning(
                                request,
                                gettext(
                                    "The selected storage slot is no longer "
                                    "available. Please choose another slot."
                                ),
                            )

                    asset = Asset.objects.create(
                        customer=customer,
                        brand=brand,
                        model_name=model_name,
                        color=color,
                        size=size,
                        status=Asset.Status.RECEIVED,
                        storage_slot=storage_slot,
                    )
                    created_assets.append(asset)
                    _attach_intake_photos(request, asset, "photos")
                    try:
                        service = ServiceType.objects.exclude(
                            category=ServiceType.Category.AI_ASSESSMENT
                        ).get(pk=service_id)
                        desc = f"{service.name} for {brand} {model_name}"
                        if color:
                            desc += f" ({color})"
                        OrderItem.objects.create(
                            order=order,
                            service_type=service,
                            asset=asset,
                            description=desc,
                            quantity=1,
                            unit_price=service.price
                        )
                    except ServiceType.DoesNotExist:
                        pass

            # ບໍລິການເສີມທີ່ຕິກໄວ້ໃນບລັອກດຽວກັນ (ຄິດຕໍ່ບິນ ບໍ່ແມ່ນຕໍ່ຄູ່)
            # ໜ້າຂາຍໜ້າຮ້ານລວມຂັ້ນຕອນ "ໃບສະເໜີລາຄາ" ເຂົ້າມາຢູ່ໜ້າດຽວກັນແລ້ວ
            extra_service_ids = [
                int(sid) for sid in request.POST.getlist("services") if sid.isdigit()
            ]
            if extra_service_ids:
                default_asset = created_assets[0] if created_assets else None
                extra_services = ServiceType.objects.filter(
                    pk__in=extra_service_ids, is_active=True
                ).exclude(category=ServiceType.Category.AI_ASSESSMENT)
                for service in extra_services:
                    OrderItem.objects.create(
                        order=order,
                        service_type=service,
                        asset=default_asset,
                        description=service.name,
                        quantity=1,
                        unit_price=service.price,
                    )

            # ສ່ວນຫຼຸດ ແລະ VAT — ຄິດຈາກລາຍການທີ່ບັນທຶກແລ້ວຈິງ ບໍ່ແມ່ນຈາກຄ່າທີ່ໜ້າຈໍສົ່ງມາ
            subtotal = sum(
                (item.subtotal for item in OrderItem.objects.filter(order=order)),
                start=0,
            )
            order.discount = promo_discount(
                subtotal, request.POST.get("promo_code", "")
            )
            vat_rate = request.POST.get("vat_rate", "")
            order.vat_rate = int(vat_rate) if vat_rate.isdigit() else order.vat_rate
            order.save(update_fields=["discount", "vat_rate", "updated_at"])

            # ອໍເດີທີ່ມີແຕ່ບໍລິການ "ຮັບຊື້ເກີບມືສອງ" ຢ່າງດຽວ (ບໍ່ມີບໍລິການທີ່ຄິດຄ່າບໍລິການ)
            # ຂ້າມການອອກໃບບິນ — ຮ້ານເປັນຝ່າຍຈ່າຍເງິນຊື້ ບໍ່ແມ່ນເກັບເງິນລູກຄ້າ
            # ຈຶ່ງບໍ່ມີຫຍັງໃຫ້ຄິດເງິນ ໃຫ້ພາໄປໜ້າ AI Grading ຂອງເກີບເລີຍ ເພື່ອຖ່າຍຮູບປະເມີນລາຄາຮັບຊື້
            order_items = list(order.items.select_related("service_type"))
            has_buyback_item = any(
                item.service_type
                and item.service_type.category == ServiceType.Category.BUYBACK
                for item in order_items
            )
            has_paid_item = any(
                item.service_type
                and item.service_type.category != ServiceType.Category.BUYBACK
                for item in order_items
            )
            buyback_only = has_buyback_item and not has_paid_item

            if (next_action == "ai_scan" or buyback_only) and created_assets:
                detail_url = reverse(
                    "asset_intake:detail", args=[created_assets[0].pk]
                )
                return redirect(f"{detail_url}?ai=1#ai-photo-upload")

            # ໜ້າດຽວຈົບ: ບໍ່ຜ່ານໃບສະເໜີລາຄາ ແລະ ບໍ່ຕ້ອງລົງລາຍເຊັນອະນຸມັດອີກ
            return redirect("pos:invoice", pk=order.pk)

    recent_orders = Order.objects.select_related("customer").prefetch_related(
        "items__service_type", "items__asset", "payments"
    )[:6]
    latest_order = recent_orders[0] if recent_orders else None
    supplies = Supply.objects.filter(is_active=True)
    care_services = ServiceType.objects.filter(is_active=True).exclude(
        category=ServiceType.Category.AI_ASSESSMENT
    ).order_by("-category", "price", "name")
    # ບໍລິການຫຼັກ = ເລືອກ 1 ຢ່າງຕໍ່ເກີບ 1 ຄູ່ / ບໍລິການເສີມ = ຕິກໄດ້ຫຼາຍຢ່າງຕໍ່ 1 ບິນ
    primary_services = [
        service
        for service in care_services
        if service.category != ServiceType.Category.ADD_ON
    ]
    addon_services = [
        service
        for service in care_services
        if service.category == ServiceType.Category.ADD_ON
    ]
    from asset_intake.models import StorageSlot

    storage_slots = StorageSlot.objects.filter(
        is_active=True, asset__isnull=True
    ).order_by("zone", "cabinet", "position")
    context = {
        "active_nav": "pos",
        # AI assessment is shown in its own panel, not mixed into shoe-care choices.
        "services": primary_services,
        "addon_services": addon_services,
        "storage_slots": storage_slots,
        "recent_orders": recent_orders,
        "latest_order": latest_order,
        "next_order_number": generate_order_number(),
        "payment_methods": Payment.Method.choices,
        "supplies": supplies,
        "stock_movements": StockMovement.objects.select_related("supply", "order")[:6],
        "low_stock_supplies": [s for s in supplies if s.is_low_stock][:5],
        # ຍີ່ຫໍ້/ລຸ້ນ ຮ້ານຈັດການເອງໄດ້ທີ່ໜ້າ /intake/brands/ — ບໍ່ຝັງແຂງໃນ template ອີກ
        "brand_catalogue": brand_catalogue(),
        # ບອກເພດານຈາກ settings ຈິງ — ຢ່າຂຽນເລກຕາຍໃນໜ້າ ບໍ່ດັ່ງນັ້ນຄ່າສອງບ່ອນຈະຄາດເຄື່ອນ
        "max_photo_mb": settings.MAX_UPLOAD_IMAGE_MB,
        "photo_slots": intake_photo_slots(),
    }
    return render(request, "pos/create_order.html", context)


@login_required
def quotation_view(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("customer").prefetch_related("items__service_type"),
        pk=pk
    )
    all_services = ServiceType.objects.filter(is_active=True)
    service_groups = build_service_groups()
    order_services = [item.service_type for item in order.items.all() if item.service_type]
    
    if request.method == "POST":
        selected_service_ids = [
            int(sid) for sid in request.POST.getlist("services") if sid.isdigit()
        ]
        promo_code = request.POST.get("promo_code", "").strip().upper()
        vat_rate = int(request.POST.get("vat_rate", 10))

        # ເກີບຂອງ *ບິນນີ້* ເທົ່ານັ້ນ — ບໍ່ດຶງເກີບຄູ່ອື່ນຂອງລູກຄ້າ (ຄູ່ຈາກການມາຄັ້ງກ່ອນ)
        # ມາຜູກ ບໍ່ດັ່ງນັ້ນຄູ່ນັ້ນຈະຖືກລັອກໄວ້ກັບຍອດຄ້າງຂອງບິນໃໝ່.
        # ອ່ານກ່ອນລຶບ ແລະ ອ່ານສົດຈາກ DB — order.items ຖືກ prefetch ໄວ້ຕອນໂຫຼດໜ້າ
        default_asset = (
            OrderItem.objects.filter(order=order, asset__isnull=False)
            .select_related("asset")
            .order_by("pk")
            .first()
        )
        default_asset = default_asset.asset if default_asset else None

        # ອັບເດດລາຍການເດີມ ບໍ່ແມ່ນລຶບແລ້ວສ້າງໃໝ່ — ການລຶບເຮັດໃຫ້ການຜູກ
        # "ບໍລິການ ↔ ເກີບແຕ່ລະຄູ່" ທີ່ POS ສ້າງໄວ້ຫາຍໄປ ແລ້ວເກີບຄູ່ທີ 2
        # ຈະຫຼຸດອອກຈາກບິນ ຈົນສົ່ງມອບຜ່ານໜ້າ POS ບໍ່ໄດ້ ແລະບ່ອນເກັບບໍ່ຖືກປົດ
        selected = set(selected_service_ids)
        kept_service_ids = set()
        for item in order.items.select_related("service_type"):
            if item.service_type_id in selected:
                # ຄູ່ 2 ຄູ່ທີ່ສັ່ງບໍລິການດຽວກັນ = 2 ແຖວ — ຮັກສາໄວ້ທັງສອງ
                kept_service_ids.add(item.service_type_id)
            else:
                item.delete()

        for service_id in selected_service_ids:
            if service_id in kept_service_ids:
                continue
            service = ServiceType.objects.filter(pk=service_id).first()
            if service is None:
                continue
            OrderItem.objects.create(
                order=order,
                service_type=service,
                asset=default_asset,
                description=service.name,
                quantity=1,
                unit_price=service.price,
            )

        # ຄິດຍອດຈາກລາຍການຈິງທີ່ບັນທຶກແລ້ວ (ນັບທຸກຄູ່) ບໍ່ແມ່ນລາຄາຕໍ່ບໍລິການອັນລະເທື່ອ
        subtotal = sum(
            item.subtotal for item in OrderItem.objects.filter(order=order)
        )

        order.discount = promo_discount(subtotal, promo_code)
        order.vat_rate = vat_rate
        order.save()
        # ບໍ່ມີຂັ້ນຕອນລົງລາຍເຊັນອະນຸມັດອີກແລ້ວ — ອອກໃບບິນເລີຍ
        return redirect("pos:invoice", pk=order.pk)


    context = {
        "active_nav": "pos",
        "order": order,
        "all_services": all_services,
        "service_groups": service_groups,
        "order_services": order_services,
    }
    return render(request, "pos/quotation.html", context)


@login_required
def invoice_view(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("customer").prefetch_related("items", "payments"),
        pk=pk,
    )
    # ຊຳລະແລ້ວ → ກຽມລິ້ງ WhatsApp ກາດ Stamp ໄວ້ໃຫ້ພະນັກງານກົດສົ່ງ
    stamp_context = {}
    if order.status == Order.Status.PAID and order.customer_id:
        from django.conf import settings

        from digital_member.models import MemberCard
        from notifications.services import build_stamp_wa_link, member_card_image_url

        card, _created = MemberCard.objects.get_or_create(customer=order.customer)
        visit_count = Order.objects.filter(
            customer=order.customer, status=Order.Status.PAID
        ).count()
        stamp_context = {
            "member_card": card,
            "visit_count": visit_count,
            "stamp_wa_link": build_stamp_wa_link(order.customer, card, visit_count),
            "stamp_card_image_url": member_card_image_url(card),
            # ຕັ້ງ Cloud API ຄົບບໍ່ → ຕັດສິນວ່າຈະສົ່ງຮູບເອງ ຫຼື ໃຫ້ພະນັກງານກົດສົ່ງ
            "whatsapp_api_ready": bool(
                settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID
            ),
        }

    return render(request, "pos/invoice.html", {"order": order, **stamp_context})


def _load_order_for_money(pk):
    """ໂຫຼດບິນພ້ອມທຸກຢ່າງທີ່ໜ້າຄິດເງິນຕ້ອງໃຊ້ — ກັນ N+1 ຕອນຄິດຍອດຄ້າງ"""
    return get_object_or_404(
        Order.objects.select_related("customer").prefetch_related(
            "items__service_type",
            "items__asset",
            "payments__received_by",
        ),
        pk=pk,
    )


def _quick_cash_options(balance, limit=2):
    """ປຸ່ມທາງລັດເງິນສົດ — ຄ່າທີ່ລູກຄ້າຍື່ນມາແທ້ໆ

    ຜະສົມສອງແນວຄິດ: ປັດຂຶ້ນຫຼັກ 10k/50k/100k (ລູກຄ້ານັບເງິນເອງ)
    ກັບ ໃບເງິນມາດຕະຖານທີ່ໃຫຍ່ກວ່າຍອດຄ້າງ (ຍື່ນໃບດຽວ).
    ຕັດຄ່າທີ່ = ຍອດຄ້າງອອກ ເພາະປຸ່ມ "ພໍດີ" ຮັບໜ້າທີ່ນັ້ນຢູ່ແລ້ວ.
    """
    if balance <= 0:
        return []

    def ceil_to(step):
        step = Decimal(step)
        return (balance / step).to_integral_value(rounding="ROUND_CEILING") * step

    candidates = {ceil_to(10000), ceil_to(50000), ceil_to(100000)}
    candidates.update(
        Decimal(n) for n in (20000, 50000, 100000, 200000, 500000, 1000000)
    )
    # ຮັບປະກັນວ່າມີຢ່າງໜ້ອຍ 1 ຄ່າ ເຖິງແມ່ນຍອດຄ້າງຈະໃຫຍ່ກວ່າໃບເງິນທຸກໃບ
    candidates.add((balance // 100000 + 1) * 100000)
    return sorted(c for c in candidates if c > balance)[:limit]


@login_required
def checkout_view(request, pk):
    """ໜ້າຄິດເງິນ — ຊ້າຍ: ບິນ (ເຫັນຕະຫຼອດ) / ຂວາ: ຮັບເງິນ"""
    order = _load_order_for_money(pk)
    balance = order.balance_due

    return render(
        request,
        "pos/checkout.html",
        {
            "active_nav": "pos",
            "order": order,
            "balance_due": balance,
            "amount_paid": order.amount_paid,
            "quick_cash": _quick_cash_options(balance),
            "payment_methods": Payment.Method.choices,
            "currencies": CURRENCY_CHOICES,
            "base_currency": BASE_CURRENCY,
            # ລະຫັດກັນບັນທຶກຊ້ຳ — ສ້າງໃໝ່ທຸກຄັ້ງທີ່ໂຫຼດໜ້າ, ສົ່ງໄປກັບຟອມ
            "idempotency_key": uuid.uuid4(),
            "assets": order.assets(),
            "can_void": get_role(request.user) == StaffProfile.Role.MANAGER,
        },
    )


@login_required
def take_payment(request, pk):
    """ບັນທຶກການຮັບເງິນ 1 ແຖວ (ຮັບໄດ້ຫຼາຍແຖວຕໍ່ 1 ບິນ = split tender)"""
    order = _load_order_for_money(pk)
    if request.method != "POST":
        return redirect("pos:checkout", pk=order.pk)

    key = request.POST.get("idempotency_key", "").strip()
    try:
        key = uuid.UUID(key) if key else None
    except ValueError:
        key = None

    try:
        payment, created = record_payment(
            order=order,
            amount=request.POST.get("amount", "").strip(),
            method=request.POST.get("method", Payment.Method.CASH),
            currency=request.POST.get("currency", BASE_CURRENCY),
            tendered=request.POST.get("tendered", "").strip() or None,
            fx_rate=request.POST.get("fx_rate", "").strip() or None,
            user=request.user,
            idempotency_key=key,
            note=request.POST.get("note", "").strip()[:200],
        )
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)
        return redirect("pos:checkout", pk=order.pk)

    if not created:
        messages.info(request, _("This payment was already recorded."))
        return redirect("pos:checkout", pk=order.pk)

    order.refresh_from_db()
    if payment.change_amount > 0:
        messages.success(
            request,
            _("Payment recorded. Change due: %(change)s %(currency)s")
            % {"change": payment.change_amount, "currency": payment.currency},
        )
    else:
        messages.success(request, _("Payment recorded."))

    if order.is_settled:
        return redirect("pos:invoice", pk=order.pk)
    return redirect("pos:checkout", pk=order.pk)


@manager_required
def void_payment_view(request, pk, payment_pk):
    """ຍົກເລີກແຖວການຊຳລະ — ສະເພາະຜູ້ຈັດການ (void ≠ ຄືນເງິນ)"""
    order = get_object_or_404(Order, pk=pk)
    payment = get_object_or_404(Payment, pk=payment_pk, order=order)

    if request.method != "POST":
        return redirect("pos:checkout", pk=order.pk)

    void_payment(
        payment=payment,
        user=request.user,
        reason=request.POST.get("reason", "").strip()[:200],
    )
    messages.success(request, _("Payment voided."))
    return redirect("pos:checkout", pk=order.pk)


@login_required
def send_stamp_card(request, pk):
    """ສົ່ງ *ຮູບ* ບັດສະສົມ Stamp ໃຫ້ລູກຄ້າໂດຍກົງຜ່ານ WhatsApp Cloud API

    ຖ້າຍັງບໍ່ໄດ້ຕັ້ງ Cloud API ຈະບອກໃຫ້ພະນັກງານໃຊ້ປຸ່ມສົ່ງເອງແທນ
    """
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    if request.method != "POST":
        return redirect("pos:invoice", pk=order.pk)

    if not order.customer_id:
        messages.error(request, _("This bill has no customer attached."))
        return redirect("pos:invoice", pk=order.pk)

    from digital_member.models import MemberCard
    from notifications.services import notify_stamp_card

    card, _created = MemberCard.objects.get_or_create(customer=order.customer)
    visit_count = Order.objects.filter(
        customer=order.customer, status=Order.Status.PAID
    ).count()

    ok, error = notify_stamp_card(order.customer, card, visit_count)
    if ok:
        messages.success(request, _("Stamp card image sent on WhatsApp."))
    else:
        messages.error(
            request,
            _("Could not send automatically (%(error)s) — use the manual button.")
            % {"error": error},
        )
    return redirect("pos:invoice", pk=order.pk)


@login_required
def mark_order_paid(request, pk):
    """ປຸ່ມດ່ວນ "ຮັບເງິນສົດເຕັມຍອດ" ຈາກໃບບິນ

    ຍັງເກັບໄວ້ເພື່ອຄວາມໄວໜ້າຮ້ານ ແຕ່ດຽວນີ້ບັນທຶກລົງ ledger ຈິງຜ່ານ
    record_payment() ບໍ່ແມ່ນປ່ຽນ status ລອຍໆຄືເກົ່າ
    """
    order = _load_order_for_money(pk)
    if request.method != "POST":
        return redirect("pos:invoice", pk=order.pk)

    balance = order.balance_due
    if balance <= 0:
        messages.info(request, _("This order is already fully paid."))
        return redirect("pos:invoice", pk=order.pk)

    try:
        record_payment(
            order=order,
            amount=balance,
            method=Payment.Method.CASH,
            currency=BASE_CURRENCY,
            user=request.user,
            note=gettext("Quick full payment from invoice"),
        )
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)
        return redirect("pos:invoice", pk=order.pk)

    order.refresh_from_db()
    if order.customer_id:
        from digital_member.models import MemberCard

        card = MemberCard.objects.filter(customer=order.customer).first()
        if card is not None:
            messages.success(
                request,
                _("Payment recorded — 1 stamp added (%(stamps)s/10).")
                % {"stamps": card.current_stamps},
            )
            return redirect("pos:invoice", pk=order.pk)

    messages.success(request, _("Payment recorded."))
    return redirect("pos:invoice", pk=order.pk)


@login_required
def open_orders(request):
    """ໜ້າ "ບິນຄ້າງ" — ປະຕູທາງເຂົ້າຕອນລູກຄ້າມາຮັບເກີບ

    ຮຽງຕາມວັນນັດຮັບເຄື່ອງທີ່ໃກ້ທີ່ສຸດກ່ອນ ແລ້ວຄ່ອຍຕາມວັນເປີດບິນ
    """
    query = request.GET.get("q", "").strip()

    # ສະແກນປ້າຍເກີບ/QR → ຖ້າຖອດລະຫັດໄດ້ບິນດຽວ ພາໄປໜ້າຄິດເງິນເລີຍ
    # ບໍ່ໃຫ້ພະນັກງານຕ້ອງກົດຊ້ຳອີກຄັ້ງ ຕອນລູກຄ້າຢືນລໍຢູ່ໜ້າເຄົາເຕີ
    if query and request.GET.get("scan") == "1":
        scanned_order = open_order_for_scan(query)
        if scanned_order is not None:
            return redirect("pos:checkout", pk=scanned_order.pk)

        # ຖອດລະຫັດໄດ້ ແຕ່ບິນປິດໄປແລ້ວ → ບອກໃຫ້ຮູ້ ຢ່າໃຫ້ໜ້າຫວ່າງລອຍໆ
        asset, order = resolve_scan_code(query)
        if asset is not None or order is not None:
            label = asset.ticket_number if asset else order.order_number
            messages.info(
                request,
                _("%(label)s has no open bill — it is already paid and collected.")
                % {"label": label},
            )
            query = label
        else:
            messages.error(
                request,
                _("Nothing matched the scanned code: %(code)s") % {"code": query},
            )

    orders = (
        Order.objects.filter(status__in=Order.OPEN_STATUSES)
        .select_related("customer")
        .prefetch_related("items__asset", "payments")
    )

    if query:
        orders = orders.filter(
            Q(order_number__icontains=query)
            | Q(customer__name__icontains=query)
            | Q(customer__phone__icontains=query)
            | Q(items__asset__ticket_number__icontains=query)
        ).distinct()

    rows = []
    for order in orders:
        assets = order.assets()
        rows.append({
            "order": order,
            "assets": assets,
            "balance_due": order.balance_due,
            "amount_paid": order.amount_paid,
            "ready_count": sum(1 for a in assets if a.status == "ready"),
            "pickup_date": min(
                (a.pickup_date for a in assets if a.pickup_date), default=None
            ),
        })

    # ບິນທີ່ນັດຮັບກ່ອນຢູ່ເທິງສຸດ; ບິນທີ່ບໍ່ມີວັນນັດໄປທ້າຍສຸດ
    rows.sort(key=lambda r: (r["pickup_date"] is None, r["pickup_date"]
                             or r["order"].created_at.date()))

    return render(
        request,
        "pos/open_orders.html",
        {
            "active_nav": "open_orders",
            "rows": rows,
            "query": query,
            "today": timezone.localdate(),
            "total_outstanding": sum(
                (r["balance_due"] for r in rows), start=Decimal("0")
            ),
        },
    )


@login_required
def handover_view(request, pk):
    """ໜ້າສົ່ງມອບເຄື່ອງ — ຕິກເປັນຄູ່ໆ, ຖືກລັອກໄວ້ຈົນກວ່າຍອດຄ້າງເປັນ 0"""
    order = _load_order_for_money(pk)
    assets = order.assets()
    balance = order.balance_due

    if request.method == "POST":
        if balance > 0:
            messages.error(
                request,
                _("Cannot hand over: %(balance)s is still due on this order.")
                % {"balance": balance},
            )
            return redirect("pos:handover", pk=order.pk)

        received_to = request.POST.get("received_to", "").strip()
        selected = set(request.POST.getlist("asset_ids"))
        if not selected:
            messages.error(request, _("Select at least one item to hand over."))
            return redirect("pos:handover", pk=order.pk)

        handed = 0
        for asset in assets:
            if str(asset.pk) not in selected:
                continue
            try:
                hand_over_asset(
                    order=order,
                    asset=asset,
                    user=request.user,
                    received_to=received_to,
                )
                handed += 1
            except ValidationError as exc:
                for message in exc.messages:
                    messages.error(request, message)

        if handed:
            messages.success(
                request,
                _("%(count)s item(s) handed over.") % {"count": handed},
            )
        return redirect("pos:handover", pk=order.pk)

    return render(
        request,
        "pos/handover.html",
        {
            "active_nav": "pos",
            "order": order,
            "assets": assets,
            "balance_due": balance,
            "all_returned": bool(assets) and all(
                a.status == "returned" for a in assets
            ),
        },
    )


@login_required
def invoice_pdf(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("customer").prefetch_related("items", "payments"),
        pk=pk,
    )
    from core.pdf_fonts import pdf_font_context, pdf_response

    html = render_to_string(
        "pos/invoice.html",
        {"order": order, "for_pdf": True, **pdf_font_context()},
    )
    return pdf_response(html, f"{order.order_number}.pdf")
