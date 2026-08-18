import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from .models import ServiceSupply, StockMovement, Supply


def _as_int(value, default=0):
    """ຟອມສົ່ງມາເປັນຂໍ້ຄວາມສະເໝີ — ຄ່າຫວ່າງ ຫຼື ພິມຜິດຕ້ອງບໍ່ພັງເປັນໜ້າ 500"""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_decimal(value, default=0):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


@login_required
def index(request):
    supplies = Supply.objects.filter(is_active=True).order_by("name")
    low_stock = [s for s in supplies if s.is_low_stock]
    movement_labels = {
        StockMovement.MovementType.IN: _("Stock in"),
        StockMovement.MovementType.OUT: _("Stock out"),
        StockMovement.MovementType.ADJUST: _("Adjustment"),
    }
    movements = list(
        StockMovement.objects.select_related("supply", "order")[:10]
    )
    for movement in movements:
        movement.localized_type = movement_labels.get(
            movement.movement_type, movement.movement_type
        )

    # ສູດອຸປະກອນ — ບໍລິການໃດໃຊ້ອຸປະກອນຫຍັງແດ່ ຢ່າງລະເທົ່າໃດ.
    # ຕາບໃດທີ່ຍັງບໍ່ມີສູດ ການຕັດສະຕັອກອັດຕະໂນມັດຈະບໍ່ຫັກຫຍັງເລີຍ ຈຶ່ງຕ້ອງ
    # ຕັ້ງໄດ້ຈາກໜ້ານີ້ ບໍ່ແມ່ນຢູ່ແຕ່ໃນ admin ທີ່ພະນັກງານຮ້ານເຂົ້າບໍ່ເຖິງ
    from pos.models import ServiceType

    services = list(
        ServiceType.objects.filter(is_active=True).prefetch_related(
            "supply_usages__supply"
        )
    )
    service_recipes = [
        {
            "service": service,
            "usages": list(service.supply_usages.all()),
        }
        for service in services
    ]

    context = {
        "active_nav": "inventory",
        "supplies": supplies,
        "low_stock_count": len(low_stock),
        "supply_count": supplies.count(),
        "movements": movements,
        "service_recipes": service_recipes,
        "services_without_recipe": sum(
            1 for row in service_recipes if not row["usages"]
        ),
        "negative_stock_count": sum(
            1 for s in supplies if s.quantity_on_hand < 0
        ),
    }
    return render(request, "inventory/index.html", context)

@login_required
def export_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="materials_inventory.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "SKU",
            _("Name"),
            _("Stock on hand"),
            _("Unit"),
            _("Reorder level"),
            _("Cost price"),
            _("Status"),
        ]
    )
    for s in Supply.objects.filter(is_active=True):
        status = _("Low stock") if s.is_low_stock else _("In stock")
        writer.writerow(
            [
                s.sku,
                s.name,
                s.quantity_on_hand,
                s.unit,
                s.reorder_level,
                s.cost_price,
                status,
            ]
        )
    return response


@login_required
def add_supply(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        sku = request.POST.get("sku", "").strip()
        unit = request.POST.get("unit", "ອັນ").strip()
        quantity_on_hand = _as_int(request.POST.get("quantity_on_hand"))
        reorder_level = _as_int(request.POST.get("reorder_level"))
        cost_price = _as_decimal(request.POST.get("cost_price"))

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
        supply.quantity_on_hand = _as_int(request.POST.get("quantity_on_hand"))
        supply.reorder_level = _as_int(request.POST.get("reorder_level"))
        supply.cost_price = _as_decimal(request.POST.get("cost_price"))
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
        quantity = _as_int(request.POST.get("quantity"))
        note = request.POST.get("note", "").strip()

        supply = get_object_or_404(Supply, pk=supply_id)
        StockMovement.objects.create(
            supply=supply,
            movement_type=movement_type,
            quantity=quantity,
            note=note
        )
    return redirect("inventory:index")


@login_required
def add_recipe(request):
    """ຕັ້ງວ່າບໍລິການໜຶ່ງໃຊ້ອຸປະກອນຫຍັງ ຢ່າງລະເທົ່າໃດ (ສູດຕັດສະຕັອກ)"""
    if request.method != "POST":
        return redirect("inventory:index")

    from pos.models import ServiceType

    service = get_object_or_404(ServiceType, pk=request.POST.get("service_type"))
    supply = get_object_or_404(Supply, pk=request.POST.get("supply"))
    quantity = _as_int(request.POST.get("quantity_per_unit"), 1)
    if quantity < 1:
        messages.error(request, _("Quantity used must be at least 1."))
        return redirect("inventory:index")

    # ສົ່ງອຸປະກອນຕົວເກົ່າມາອີກ = ຢາກແກ້ຈຳນວນ ບໍ່ແມ່ນເພີ່ມແຖວຊ້ຳ
    # (ແຖວຊ້ຳຈະເຮັດໃຫ້ຫັກສະຕັອກສອງເທື່ອຈາກບໍລິການດຽວ ຈຶ່ງມີ unique constraint ກັນໄວ້)
    _recipe, created = ServiceSupply.objects.update_or_create(
        service_type=service,
        supply=supply,
        defaults={"quantity_per_unit": quantity},
    )
    if created:
        messages.success(request, _("Material added to the service recipe."))
    else:
        messages.success(request, _("Updated the quantity for this material."))

    return redirect("inventory:index")


@login_required
def delete_recipe(request, pk):
    recipe = get_object_or_404(ServiceSupply, pk=pk)
    if request.method == "POST":
        recipe.delete()
        messages.success(request, _("Material removed from the service recipe."))
    return redirect("inventory:index")
