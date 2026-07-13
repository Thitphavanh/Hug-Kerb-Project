from django.urls import path

from . import views

app_name = "crm"

urlpatterns = [
    path("", views.index, name="index"),
    path("customers/<int:pk>/edit/", views.edit_customer, name="edit_customer"),
    path("customers/<int:pk>/delete/", views.delete_customer, name="delete_customer"),
]
