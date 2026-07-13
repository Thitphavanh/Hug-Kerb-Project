from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "line_id", "created_at"]
    search_fields = ["name", "phone", "email", "line_id", "telegram_chat_id", "facebook"]
    list_filter = ["created_at"]
    readonly_fields = ["created_at", "updated_at"]
