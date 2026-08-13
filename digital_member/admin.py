from django.contrib import admin

from .models import MemberCard, PointTransaction, StampTransaction


class PointTransactionInline(admin.TabularInline):
    model = PointTransaction
    extra = 0
    readonly_fields = ["created_at"]


class StampTransactionInline(admin.TabularInline):
    model = StampTransaction
    extra = 0
    readonly_fields = ["created_at"]


@admin.register(MemberCard)
class MemberCardAdmin(admin.ModelAdmin):
    list_display = ["card_number", "customer", "tier", "points_balance", "stamps_count", "stamps_redeemed", "is_active"]
    list_filter = ["tier", "is_active"]
    search_fields = ["card_number", "customer__name", "customer__phone"]
    readonly_fields = ["card_number", "points_balance", "issued_at"]
    autocomplete_fields = ["customer"]
    inlines = [PointTransactionInline, StampTransactionInline]


@admin.register(PointTransaction)
class PointTransactionAdmin(admin.ModelAdmin):
    list_display = ["card", "points", "reason", "order", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["card__card_number", "card__customer__name", "reason"]
    autocomplete_fields = ["card", "order"]


@admin.register(StampTransaction)
class StampTransactionAdmin(admin.ModelAdmin):
    list_display = ["card", "action", "count", "note", "created_at"]
    list_filter = ["action", "created_at"]
    search_fields = ["card__card_number", "card__customer__name", "note"]
    autocomplete_fields = ["card"]

