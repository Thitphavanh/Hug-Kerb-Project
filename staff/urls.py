from django.urls import path

from . import views

app_name = "staff"

urlpatterns = [
    path("commissions/", views.commission_report, name="commissions"),
    path("add/", views.add_staff, name="add"),
    path("<int:pk>/edit/", views.edit_staff, name="edit"),
    path("<int:pk>/delete/", views.delete_staff, name="delete"),
]
