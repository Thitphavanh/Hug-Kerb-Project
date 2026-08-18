from django.urls import path

from . import views

app_name = "pos"

urlpatterns = [
    path("create/", views.create_order, name="create"),
    path("orders/", views.open_orders, name="open_orders"),
    path("api/customers/search/", views.customer_search, name="customer_search"),
    path("api/scan-lookup/", views.scan_lookup, name="scan_lookup"),
    path("api/storage-map/", views.storage_map_data, name="storage_map_data"),
    path("orders/<int:pk>/quotation/", views.quotation_view, name="quotation"),
    path("orders/<int:pk>/checkout/", views.checkout_view, name="checkout"),
    path("orders/<int:pk>/payments/", views.take_payment, name="take_payment"),
    path(
        "orders/<int:pk>/payments/<int:payment_pk>/void/",
        views.void_payment_view,
        name="void_payment",
    ),
    path("orders/<int:pk>/handover/", views.handover_view, name="handover"),
    path("orders/<int:pk>/invoice/", views.invoice_view, name="invoice"),
    path("orders/<int:pk>/mark-paid/", views.mark_order_paid, name="mark_paid"),
    path("orders/<int:pk>/send-stamp-card/", views.send_stamp_card, name="send_stamp_card"),
    path("orders/<int:pk>/invoice.pdf", views.invoice_pdf, name="invoice_pdf"),
]
