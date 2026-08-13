from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Expense, Order, OrderItem, Payment, ServiceType


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "work_type", "price", "is_active"]
    list_filter = ["category", "work_type", "is_active"]
    list_editable = ["work_type"]
    search_fields = ["name"]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    autocomplete_fields = ["service_type", "asset"]


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    # ledger ບໍ່ໃຫ້ແກ້ຍ້ອນຫຼັງ — ອ່ານໄດ້ຢ່າງດຽວ, ຈະຍົກເລີກໃຫ້ໃຊ້ໜ້າຄິດເງິນ
    fields = ["kind", "amount", "currency", "method", "base_amount", "paid_at", "voided_at"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "order_number",
        "customer",
        "status",
        "total_display",
        "balance_display",
        "created_at",
        "invoice_link",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["order_number", "customer__name", "customer__phone"]
    readonly_fields = [
        "order_number",
        "status",
        "total_snapshot",
        "settled_at",
        "created_at",
        "updated_at",
    ]
    autocomplete_fields = ["customer"]
    inlines = [OrderItemInline, PaymentInline]

    @admin.display(description="ຍອດລວມ")
    def total_display(self, obj):
        return obj.effective_total

    @admin.display(description="ຍອດຄ້າງ")
    def balance_display(self, obj):
        return obj.balance_due

    @admin.display(description="ໃບບິນ")
    def invoice_link(self, obj):
        url = reverse("pos:invoice", args=[obj.pk])
        return format_html('<a href="{}" target="_blank">🖨️ ພິມ</a>', url)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "order",
        "kind",
        "amount",
        "currency",
        "base_amount",
        "method",
        "paid_at",
        "voided_at",
    ]
    list_filter = ["kind", "method", "currency", "paid_at", "voided_at"]
    search_fields = ["order__order_number", "order__customer__name"]
    autocomplete_fields = ["order"]
    readonly_fields = [
        "paid_at",
        "base_amount",
        "idempotency_key",
        "voided_at",
        "voided_by",
    ]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["date", "category", "description", "amount", "currency"]
    list_filter = ["category", "date"]
    search_fields = ["description"]
