from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.template.loader import render_to_string
from xhtml2pdf import pisa

from inventory.models import StockMovement, Supply

from .models import Order, OrderItem, Payment, ServiceType, generate_order_number


@login_required
def create_order(request):
    if request.method == "POST":
        customer_name = request.POST.get("customer_name", "").strip()
        customer_phone = request.POST.get("customer_phone", "").strip()

        if customer_name and customer_phone:
            from crm.models import Customer
            from asset_intake.models import Asset

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

            if indices:
                # Multi-item processing
                for idx in indices:
                    brand = request.POST.get(f"brand_{idx}", "").strip()
                    model_name = request.POST.get(f"model_name_{idx}", "").strip()
                    size = request.POST.get(f"size_{idx}", "").strip()
                    service_id = request.POST.get(f"service_{idx}", "")

                    if brand or model_name:
                        # Create Asset
                        asset = Asset.objects.create(
                            customer=customer,
                            brand=brand,
                            model_name=model_name,
                            size=size,
                            status=Asset.Status.RECEIVED
                        )

                        # Create OrderItem
                        try:
                            service = ServiceType.objects.get(pk=service_id)
                            OrderItem.objects.create(
                                order=order,
                                service_type=service,
                                asset=asset,
                                description=f"{service.name} for {brand} {model_name}",
                                quantity=1,
                                unit_price=service.price
                            )
                        except ServiceType.DoesNotExist:
                            pass
            else:
                # Single fallback item
                brand = request.POST.get("brand", "").strip()
                model_name = request.POST.get("model_name", "").strip()
                size = request.POST.get("size", "").strip()
                service_id = request.POST.get("service", "")
                
                if brand or model_name:
                    asset = Asset.objects.create(
                        customer=customer,
                        brand=brand,
                        model_name=model_name,
                        size=size,
                        status=Asset.Status.RECEIVED
                    )
                    try:
                        service = ServiceType.objects.get(pk=service_id)
                        OrderItem.objects.create(
                            order=order,
                            service_type=service,
                            asset=asset,
                            description=f"{service.name} for {brand} {model_name}",
                            quantity=1,
                            unit_price=service.price
                        )
                    except ServiceType.DoesNotExist:
                        pass

            return redirect("pos:quotation", pk=order.pk)

    recent_orders = Order.objects.select_related("customer").prefetch_related(
        "items__service_type", "items__asset", "payments"
    )[:6]
    latest_order = recent_orders[0] if recent_orders else None
    supplies = Supply.objects.filter(is_active=True)
    context = {
        "active_nav": "pos",
        "services": ServiceType.objects.filter(is_active=True)[:8],
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
    order_services = [item.service_type for item in order.items.all() if item.service_type]
    
    if request.method == "POST":
        selected_service_ids = request.POST.getlist("services")
        promo_code = request.POST.get("promo_code", "").strip().upper()
        
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
        "order": order,
        "all_services": all_services,
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
        
    # Calculate tax (VAT 10%)
    vat_amount = int((order.subtotal - order.discount) / 10)
    total_amount = order.subtotal - order.discount + vat_amount
    
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
    html = render_to_string("pos/invoice.html", {"order": order, "for_pdf": True})
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{order.order_number}.pdf"'
    pisa.CreatePDF(html, dest=response)
    return response
