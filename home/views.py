from django.shortcuts import render

from asset_intake.models import Asset
from crm.models import Customer
from inventory.models import Supply
from pos.models import Order, ServiceType


def index(request):
    active_supplies = Supply.objects.filter(is_active=True)
    context = {
        "service_count": ServiceType.objects.filter(is_active=True).count(),
        "open_order_count": Order.objects.exclude(status=Order.Status.CANCELLED).count(),
        "customer_count": Customer.objects.count(),
        "active_asset_count": Asset.objects.exclude(status=Asset.Status.RETURNED).count(),
        "low_stock_count": sum(1 for supply in active_supplies if supply.is_low_stock),
    }
    return render(request, "home/index.html", context)
