from django.contrib import admin

from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("asset", "channel", "recipient", "is_sent", "created_at")
    list_filter = ("channel", "is_sent")
    search_fields = ("asset__ticket_number", "recipient")
    readonly_fields = ("created_at",)
