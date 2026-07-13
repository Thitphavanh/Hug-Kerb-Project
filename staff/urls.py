from django.urls import path

from . import views

app_name = "staff"

urlpatterns = [
    path("commissions/", views.commission_report, name="commissions"),
]
