from django.contrib import admin

from .models import AccountCategory, Budget, CashBook, CashHandover


@admin.register(AccountCategory)
class AccountCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "transaction_type", "is_active", "sort_order"]
    list_filter = ["transaction_type", "is_active"]
    search_fields = ["name"]
    list_editable = ["is_active", "sort_order"]


@admin.register(CashBook)
class CashBookAdmin(admin.ModelAdmin):
    list_display = [
        "date",
        "time",
        "description",
        "transaction_type",
        "category",
        "amount",
        "currency",
        "status",
        "created_by",
    ]
    list_filter = ["transaction_type", "currency", "payment_method", "status", "date"]
    search_fields = ["description", "reference", "note"]
    date_hierarchy = "date"
    autocomplete_fields = ["category", "created_by", "updated_by"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ["month", "category", "amount", "currency"]
    list_filter = ["currency", "month"]
    autocomplete_fields = ["category"]


@admin.register(CashHandover)
class CashHandoverAdmin(admin.ModelAdmin):
    list_display = [
        "date",
        "currency",
        "expected_amount",
        "counted_amount",
        "difference_display",
        "handed_by",
        "received_by",
    ]
    list_filter = ["currency", "date"]
    readonly_fields = ["expected_amount", "created_at", "updated_at"]

    @admin.display(description="ສ່ວນຕ່າງ")
    def difference_display(self, obj):
        return obj.difference

