from django.contrib import admin

from .models import BackupRun, MediaFile


@admin.register(MediaFile)
class MediaFileAdmin(admin.ModelAdmin):
    list_display = [
        "asset",
        "stage",
        "media_type",
        "uploaded_by",
        "backed_up",
        "note",
        "uploaded_at",
    ]
    list_filter = ["stage", "media_type", "backed_up_at", "uploaded_at"]
    search_fields = ["asset__ticket_number", "asset__brand", "note", "checksum"]
    autocomplete_fields = ["asset", "uploaded_by"]
    # ຄ່າພວກນີ້ຄິດມາຈາກໄຟລ໌ຈິງ/ຮອບສຳຮອງ — ແກ້ດ້ວຍມືແລ້ວມັນຈະຕົວະ
    readonly_fields = [
        "uploaded_at",
        "checksum",
        "size_bytes",
        "backed_up_at",
        "backup_ref",
    ]

    @admin.display(description="ສຳຮອງແລ້ວ", boolean=True)
    def backed_up(self, obj):
        return obj.is_backed_up


@admin.register(BackupRun)
class BackupRunAdmin(admin.ModelAdmin):
    list_display = [
        "started_at",
        "status",
        "destination",
        "files_copied",
        "files_failed",
        "finished_at",
    ]
    list_filter = ["status", "started_at"]
    search_fields = ["destination", "detail"]
    # ປະຫວັດການສຳຮອງເປັນຫຼັກຖານ — ຕ້ອງອ່ານໄດ້ຢ່າງດຽວ
    readonly_fields = [
        field.name for field in BackupRun._meta.fields
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
