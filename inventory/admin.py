from django.contrib import admin

from .models import ServiceSupply, StockMovement, Supply


@admin.register(ServiceSupply)
class ServiceSupplyAdmin(admin.ModelAdmin):
    list_display = ["service_type", "supply", "quantity_per_unit"]
    list_filter = ["service_type"]
    search_fields = ["service_type__name", "supply__name", "supply__sku"]
    autocomplete_fields = ["service_type", "supply"]
    list_editable = ["quantity_per_unit"]


@admin.register(Supply)
class SupplyAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "sku",
        "quantity_on_hand",
        "unit",
        "reorder_level",
        "low_stock_display",
        "is_active",
    ]
    list_filter = ["is_active"]
    search_fields = ["name", "sku"]
    readonly_fields = ["quantity_on_hand", "created_at"]

    @admin.display(description="ໃກ້ໝົດ", boolean=True)
    def low_stock_display(self, obj):
        return obj.is_low_stock


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ["supply", "movement_type", "quantity", "note", "order", "created_at"]
    list_filter = ["movement_type", "created_at"]
    search_fields = ["supply__name", "supply__sku", "note"]
    autocomplete_fields = ["supply", "order"]
    readonly_fields = ["created_at"]
