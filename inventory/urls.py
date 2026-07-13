from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.index, name="index"),
    path("export/", views.export_csv, name="export_csv"),
    path("supplies/add/", views.add_supply, name="add_supply"),
    path("supplies/<int:pk>/edit/", views.edit_supply, name="edit_supply"),
    path("supplies/<int:pk>/delete/", views.delete_supply, name="delete_supply"),
    path("movements/add/", views.add_movement, name="add_movement"),
]
