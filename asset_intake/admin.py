from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from media_backup.models import MediaFile

from .models import Asset, AssetService, Brand, ShoeModel, StorageSlot


class MediaFileInline(admin.TabularInline):
    model = MediaFile
    extra = 0
    readonly_fields = ["uploaded_at"]


class AssetServiceInline(admin.TabularInline):
    """ວຽກບໍລິການຂອງຄູ່ນີ້ — ຊັກ / ສ້ອມແປງ / ປະເມີນ ແຍກແຖວກັນ"""

    model = AssetService
    extra = 0
    autocomplete_fields = ["service_type"]
    fields = ["service_type", "work_type", "status", "assigned_to", "finished_at"]
    readonly_fields = ["work_type", "finished_at"]


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = [
        "ticket_number",
        "customer",
        "brand",
        "model_name",
        "size",
        "status",
        "intake_date",
        "pickup_date",
        "ticket_link",
    ]
    list_filter = ["status", "brand", "intake_date"]
    search_fields = ["ticket_number", "brand", "model_name", "customer__name", "customer__phone"]
    readonly_fields = ["ticket_number", "intake_date", "updated_at"]
    autocomplete_fields = ["customer"]
    inlines = [AssetServiceInline, MediaFileInline]

    @admin.display(description="ໃບນັດຮັບ")
    def ticket_link(self, obj):
        url = reverse("asset_intake:ticket_view", args=[obj.pk])
        return format_html('<a href="{}" target="_blank">🖨️ ພິມ</a>', url)


@admin.register(StorageSlot)
class StorageSlotAdmin(admin.ModelAdmin):
    list_display = ["code", "zone", "cabinet", "position", "is_active", "occupant"]
    list_filter = ["zone", "cabinet", "is_active"]
    search_fields = ["zone"]



    @admin.display(description="ເກີບທີ່ເກັບຢູ່")
    def occupant(self, obj):
        return getattr(obj, "asset", None) or "—"


class ShoeModelInline(admin.TabularInline):
    model = ShoeModel
    extra = 1


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ["name", "sort_order", "model_count", "is_active"]
    list_editable = ["sort_order", "is_active"]
    search_fields = ["name"]
    inlines = [ShoeModelInline]

    @admin.display(description="ຈຳນວນລຸ້ນ")
    def model_count(self, obj):
        return obj.shoe_models.count()


@admin.register(ShoeModel)
class ShoeModelAdmin(admin.ModelAdmin):
    list_display = ["name", "brand", "is_active"]
    list_filter = ["brand", "is_active"]
    search_fields = ["name", "brand__name"]
    autocomplete_fields = ["brand"]
