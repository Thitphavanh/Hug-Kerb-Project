from django.shortcuts import redirect
from django.urls import path

from . import views

app_name = "resell_pricing_engine"

urlpatterns = [
    path("", lambda r: redirect("asset_intake:list")),
    path("assets/<int:pk>/valuate/", views.run_valuation, name="run_valuation"),
    path("assets/<int:pk>/promo/", views.run_promo, name="run_promo"),
]
