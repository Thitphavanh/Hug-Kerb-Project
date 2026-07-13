from django.contrib import admin

from .models import Assessment, AssessmentItem, ChecklistItem


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "max_score", "display_order", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name"]
    list_editable = ["display_order", "is_active"]


class AssessmentItemInline(admin.TabularInline):
    model = AssessmentItem
    extra = 0


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ["asset", "status", "overall_grade", "total_score", "ai_model", "created_at"]
    list_filter = ["status", "overall_grade", "created_at"]
    search_fields = ["asset__ticket_number", "asset__brand"]
    readonly_fields = ["created_at"]
    autocomplete_fields = ["asset"]
    inlines = [AssessmentItemInline]
