from django.contrib import admin

from .models import PriceValuation, PromoContent


@admin.register(PriceValuation)
class PriceValuationAdmin(admin.ModelAdmin):
    list_display = [
        "asset",
        "suggested_price",
        "price_min",
        "price_max",
        "currency",
        "ai_model",
        "created_at",
    ]
    list_filter = ["currency", "created_at"]
    search_fields = ["asset__ticket_number", "asset__brand"]
    readonly_fields = ["created_at"]
    autocomplete_fields = ["asset", "assessment"]


@admin.register(PromoContent)
class PromoContentAdmin(admin.ModelAdmin):
    list_display = ["asset", "platform", "ai_model", "created_at"]
    list_filter = ["platform", "created_at"]
    search_fields = ["asset__ticket_number", "content"]
    readonly_fields = ["created_at"]
    autocomplete_fields = ["asset"]
