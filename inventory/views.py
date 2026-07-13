from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import StockMovement, Supply


@login_required
def index(request):
    supplies = Supply.objects.filter(is_active=True).order_by("name")
    low_stock = [s for s in supplies if s.is_low_stock]

    context = {
        "active_nav": "inventory",
        "supplies": supplies,
        "low_stock_count": len(low_stock),
        "supply_count": supplies.count(),
        "movements": StockMovement.objects.select_related("supply", "order")[:10],
    }
    return render(request, "inventory/index.html", context)


import csv
from django.http import HttpResponse

@login_required
def export_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="materials_inventory.csv"'
    writer = csv.writer(response)
    writer.writerow(["SKU", "Name", "Stock On Hand", "Unit", "Reorder Level", "Cost Price", "Status"])
    for s in Supply.objects.filter(is_active=True):
        status = "Low Stock" if s.is_low_stock else "In Stock"
        writer.writerow([s.sku, s.name, s.quantity_on_hand, s.unit, s.reorder_level, s.cost_price, status])
    return response


@login_required
def add_supply(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        sku = request.POST.get("sku", "").strip()
        unit = request.POST.get("unit", "ອັນ").strip()
        quantity_on_hand = int(request.POST.get("quantity_on_hand", 0))
        reorder_level = int(request.POST.get("reorder_level", 0))
        cost_price = float(request.POST.get("cost_price", 0))

        Supply.objects.create(
            name=name,
            sku=sku,
            unit=unit,
            quantity_on_hand=quantity_on_hand,
            reorder_level=reorder_level,
            cost_price=cost_price
        )
    return redirect("inventory:index")


@login_required
def edit_supply(request, pk):
    supply = get_object_or_404(Supply, pk=pk)
    if request.method == "POST":
        supply.name = request.POST.get("name", "").strip()
        supply.sku = request.POST.get("sku", "").strip()
        supply.unit = request.POST.get("unit", "").strip()
        supply.quantity_on_hand = int(request.POST.get("quantity_on_hand", 0))
        supply.reorder_level = int(request.POST.get("reorder_level", 0))
        supply.cost_price = float(request.POST.get("cost_price", 0))
        supply.save()
    return redirect("inventory:index")


@login_required
def delete_supply(request, pk):
    supply = get_object_or_404(Supply, pk=pk)
    if request.method == "POST":
        supply.is_active = False
        supply.save()
    return redirect("inventory:index")


@login_required
def add_movement(request):
    if request.method == "POST":
        supply_id = request.POST.get("supply")
        movement_type = request.POST.get("movement_type")
        quantity = int(request.POST.get("quantity", 0))
        note = request.POST.get("note", "").strip()

        supply = get_object_or_404(Supply, pk=supply_id)
        StockMovement.objects.create(
            supply=supply,
            movement_type=movement_type,
            quantity=quantity,
            note=note
        )
    return redirect("inventory:index")
