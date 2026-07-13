from django.urls import path

from . import views

app_name = "pos"

urlpatterns = [
    path("create/", views.create_order, name="create"),
    path("api/scan-lookup/", views.scan_lookup, name="scan_lookup"),
    path("orders/<int:pk>/quotation/", views.quotation_view, name="quotation"),
    path("orders/<int:pk>/quotation/sign/", views.quotation_sign_view, name="quotation_sign"),
    path("orders/<int:pk>/invoice/", views.invoice_view, name="invoice"),
    path("orders/<int:pk>/invoice.pdf", views.invoice_pdf, name="invoice_pdf"),
]
