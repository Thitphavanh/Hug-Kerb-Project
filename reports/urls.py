from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.income_expense, name="income_expense"),
    path("services/", views.service_usage, name="service_usage"),
]
