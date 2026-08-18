from django.urls import path

from . import views

app_name = "asset_intake"

urlpatterns = [
    path("", views.intake_list, name="list"),
    path("new/", views.intake_create, name="create"),
    path("<int:pk>/", views.intake_detail, name="detail"),
    path("<int:pk>/edit/", views.asset_edit, name="edit"),
    path("<int:pk>/delete/", views.asset_delete, name="delete"),
    path("<int:pk>/ticket/", views.ticket_view, name="ticket_view"),
    path("<int:pk>/ticket.pdf", views.ticket_pdf, name="ticket_pdf"),
    path("<int:pk>/tag/", views.tag_label, name="tag_label"),
    path("<int:pk>/social.png", views.social_image, name="social_image"),
    path("kanban/", views.kanban_board, name="kanban"),
    path("kanban/update/", views.kanban_update_status, name="kanban_update"),
    path("service/update/", views.service_update, name="service_update"),
    path("brands/", views.brand_list, name="brands"),
    path("brands/add/", views.brand_create, name="brand_create"),
    path("brands/<int:pk>/edit/", views.brand_update, name="brand_update"),
    path("brands/<int:pk>/delete/", views.brand_delete, name="brand_delete"),
    path("brands/<int:brand_pk>/models/add/", views.shoe_model_create, name="model_create"),
    path("models/<int:pk>/delete/", views.shoe_model_delete, name="model_delete"),
    path("storage/", views.storage_map, name="storage"),
    path("storage/assign/", views.storage_assign, name="storage_assign"),
    path("storage/release/", views.storage_release, name="storage_release"),
]
