"""
URL configuration for core project.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.utils.translation import gettext_lazy as _
from django.views.generic import RedirectView

admin.site.site_header = _("Hug ເກີບ — Shop Management")
admin.site.site_title = "Hug ເກີບ Admin"
admin.site.index_title = _("Management")

urlpatterns = [
    path(
        "favicon.ico",
        RedirectView.as_view(
            url=f"{settings.STATIC_URL}images/hug-kerb-favicon-rounded.png",
            permanent=True,
        ),
        name="favicon",
    ),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("home.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("accounting/", include("accounting.urls")),
    path("reports/", include("reports.urls")),
    path("crm/", include("crm.urls")),
    path("inventory/", include("inventory.urls")),
    path("intake/", include("asset_intake.urls")),
    path("ai/", include("ai_mart_grading.urls")),
    path("pricing/", include("resell_pricing_engine.urls")),
    path("pos/", include("pos.urls")),
    path("portal/", include("digital_member.urls")),
    path("staff/", include("staff.urls")),
]

# ເສີບໄຟລ໌ media (ຮູບ/ວິດີໂອຫຼັກຖານ) ໃນໂໝດ dev
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
