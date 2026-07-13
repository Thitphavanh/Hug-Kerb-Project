from django.contrib import admin

from .models import MediaFile


@admin.register(MediaFile)
class MediaFileAdmin(admin.ModelAdmin):
    list_display = ["asset", "stage", "media_type", "note", "uploaded_at"]
    list_filter = ["stage", "media_type", "uploaded_at"]
    search_fields = ["asset__ticket_number", "asset__brand", "note"]
    autocomplete_fields = ["asset"]
    readonly_fields = ["uploaded_at"]
