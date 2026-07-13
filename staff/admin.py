from django.contrib import admin

from .models import StaffProfile


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone", "commission_rate", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("user__username", "user__first_name", "phone")
