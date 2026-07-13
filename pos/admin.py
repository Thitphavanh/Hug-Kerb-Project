from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Expense, Order, OrderItem, Payment, ServiceType


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "price", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    autocomplete_fields = ["service_type", "asset"]


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ["paid_at"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "order_number",
        "customer",
        "status",
        "total_display",
        "created_at",
        "invoice_link",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["order_number", "customer__name", "customer__phone"]
    readonly_fields = ["order_number", "created_at", "updated_at"]
    autocomplete_fields = ["customer"]
    inlines = [OrderItemInline, PaymentInline]

    @admin.display(description="ຍອດລວມ")
    def total_display(self, obj):
        return obj.total

    @admin.display(description="ໃບບິນ")
    def invoice_link(self, obj):
        url = reverse("pos:invoice", args=[obj.pk])
        return format_html('<a href="{}" target="_blank">🖨️ ພິມ</a>', url)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["order", "amount", "currency", "method", "paid_at"]
    list_filter = ["method", "currency", "paid_at"]
    search_fields = ["order__order_number", "order__customer__name"]
    autocomplete_fields = ["order"]
    readonly_fields = ["paid_at"]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["date", "category", "description", "amount", "currency"]
    list_filter = ["category", "date"]
    search_fields = ["description"]
