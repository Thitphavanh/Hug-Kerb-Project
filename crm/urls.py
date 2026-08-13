from django.urls import path

from . import views

app_name = "crm"

urlpatterns = [
    path("", views.index, name="index"),
    path("customers/<int:pk>/edit/", views.edit_customer, name="edit_customer"),
    path("customers/<int:pk>/delete/", views.delete_customer, name="delete_customer"),
    path("customers/<int:pk>/add-stamp/", views.add_stamp, name="add_stamp"),
    path("customers/<int:pk>/redeem-discount/", views.redeem_discount, name="redeem_discount"),
    path("customers/<int:pk>/reset-stamps/", views.reset_stamps, name="reset_stamps"),
]

