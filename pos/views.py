import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext

from inventory.models import StockMovement, Supply

from .models import Order, OrderItem, Payment, ServiceType, generate_order_number


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
    from asset_intake.models import StorageSlot

    slots = StorageSlot.objects.filter(is_active=True).select_related(
        "asset", "asset__customer"
    )

    zones = {}
    total = free = 0
    for slot in slots:
        occupant = getattr(slot, "asset", None)
        total += 1
        if occupant is None:
            free += 1
        zones.setdefault(slot.zone, {}).setdefault(slot.cabinet, []).append({
            "id": slot.pk,
            "code": slot.code,
            "free": occupant is None,
            "ticket_number": occupant.ticket_number if occupant else "",
            "customer_name": occupant.customer.name if occupant else "",
            "brand_model": (
                f"{occupant.brand} {occupant.model_name}".strip() if occupant else ""
            ),
        })

    zone_list = [
        {
            "name": zone,
            "cabinets": [
                {"number": cab, "slots": items} for cab, items in cabinets.items()
            ],
        }
        for zone, cabinets in zones.items()
    ]

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
    from asset_intake.models import Asset

    code = request.GET.get("code", "").strip()
    if not code:
        return JsonResponse({"found": False, "error": "empty"}, status=400)

    asset = None
    order = None

    if code.lower().startswith(("http://", "https://")):
        # QR ໜ້າ portal ລູກຄ້າ: .../t/<token>/
        m = re.search(r"/t/([A-Za-z0-9_-]+)/?", code)
        if m:
            asset = Asset.objects.select_related("customer").filter(
                public_token=m.group(1)
            ).first()
        else:
            # QR ປ້າຍແທັກຫ້ອຍເກີບ: ເປັນ URL ໜ້າລາຍລະອຽດ ລົງທ້າຍດ້ວຍ /<pk>/
            m = re.search(r"/(\d+)/?(?:[?#].*)?$", code)
            if m:
                asset = Asset.objects.select_related("customer").filter(
                    pk=int(m.group(1))
                ).first()
    elif code.upper().startswith("ORD"):
        order = Order.objects.select_related("customer").filter(
            order_number__iexact=code
        ).first()
    else:
        asset = Asset.objects.select_related("customer").filter(
            ticket_number__iexact=code
        ).first()
        if asset is None:
            asset = Asset.objects.select_related("customer").filter(
                public_token=code
            ).first()

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


@login_required
def create_order(request):
    if request.method == "POST":
        next_action = request.POST.get("next_action", "quotation")
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

            # ອໍເດີທີ່ມີແຕ່ບໍລິການ "ຮັບຊື້ເກີບມືສອງ" ຢ່າງດຽວ (ບໍ່ມີບໍລິການທີ່ຄິດຄ່າບໍລິການ)
            # ຂ້າມຂັ້ນຕອນໃບສະເໜີລາຄາ/ເຊັນຢືນຢັນ — ຮ້ານເປັນຝ່າຍຈ່າຍເງິນຊື້ ບໍ່ແມ່ນເກັບເງິນລູກຄ້າ
            # ຈຶ່ງບໍ່ມີຫຍັງໃຫ້ "ສະເໜີລາຄາ" ໃຫ້ພາໄປໜ້າ AI Grading ຂອງເກີບເລີຍ ເພື່ອຖ່າຍຮູບປະເມີນລາຄາຮັບຊື້
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

            return redirect("pos:quotation", pk=order.pk)

    recent_orders = Order.objects.select_related("customer").prefetch_related(
        "items__service_type", "items__asset", "payments"
    )[:6]
    latest_order = recent_orders[0] if recent_orders else None
    supplies = Supply.objects.filter(is_active=True)
    care_services = ServiceType.objects.filter(is_active=True).exclude(
        category=ServiceType.Category.AI_ASSESSMENT
    ).order_by("-category", "price", "name")
    from asset_intake.models import StorageSlot

    storage_slots = StorageSlot.objects.filter(
        is_active=True, asset__isnull=True
    ).order_by("zone", "cabinet", "position")
    context = {
        "active_nav": "pos",
        # AI assessment is shown in its own panel, not mixed into shoe-care choices.
        "services": care_services,
        "storage_slots": storage_slots,
        "recent_orders": recent_orders,
        "latest_order": latest_order,
        "next_order_number": generate_order_number(),
        "payment_methods": Payment.Method.choices,
        "supplies": supplies,
        "stock_movements": StockMovement.objects.select_related("supply", "order")[:6],
        "low_stock_supplies": [s for s in supplies if s.is_low_stock][:5],
    }
    return render(request, "pos/create_order.html", context)


@login_required
def quotation_view(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("customer").prefetch_related("items__service_type"),
        pk=pk
    )
    all_services = ServiceType.objects.filter(is_active=True)
    service_groups = [
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
    order_services = [item.service_type for item in order.items.all() if item.service_type]
    
    if request.method == "POST":
        selected_service_ids = request.POST.getlist("services")
        promo_code = request.POST.get("promo_code", "").strip().upper()
        vat_rate = int(request.POST.get("vat_rate", 10))
        
        # Clear existing items
        order.items.all().delete()
        
        # Calculate subtotal first to apply percentage discount
        subtotal = 0
        services_to_add = []
        for service_id in selected_service_ids:
            try:
                service = ServiceType.objects.get(pk=service_id)
                subtotal += service.price
                services_to_add.append(service)
            except ServiceType.DoesNotExist:
                pass
                
        # Calculate discount
        discount_amount = 0
        if promo_code == "KVAIPRO20":
            discount_amount = int(subtotal * 20 / 100)
        elif promo_code == "RAINY15":
            discount_amount = 15000
        elif promo_code == "MISSYOU25":
            discount_amount = 25000
            
        order.discount = discount_amount
        order.vat_rate = vat_rate
        
        # Get first asset of this customer if any
        customer_asset = order.customer.assets.first() if order.customer else None
        
        for service in services_to_add:
            OrderItem.objects.create(
                order=order,
                service_type=service,
                asset=customer_asset,
                description=service.name,
                quantity=1,
                unit_price=service.price
            )
            
        order.save()
        # Redirect to step 3 signature page
        return redirect("pos:quotation_sign", pk=order.pk)
        
    context = {
        "active_nav": "pos",
        "order": order,
        "all_services": all_services,
        "service_groups": service_groups,
        "order_services": order_services,
    }
    return render(request, "pos/quotation.html", context)


@login_required
def quotation_sign_view(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("customer").prefetch_related("items__service_type"),
        pk=pk
    )
    
    if request.method == "POST":
        signature_data = request.POST.get("signature_data", "")
        signer_name = request.POST.get("signer_name", "").strip()
        signer_title = request.POST.get("signer_title", "").strip()
        
        if signature_data:
            order.note = f"Authorized by {signer_name} ({signer_title}) via Digital Signature.\n{order.note}"
            order.save()
            
        return redirect("pos:invoice", pk=order.pk)
        
    # Calculate tax based on order.vat_rate
    vat_amount = order.vat_amount
    total_amount = order.total
    
    context = {
        "order": order,
        "vat_amount": vat_amount,
        "total_amount": total_amount,
    }
    return render(request, "pos/quotation_sign.html", context)


@login_required
def invoice_view(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("customer").prefetch_related("items", "payments"),
        pk=pk,
    )
    return render(request, "pos/invoice.html", {"order": order})


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
