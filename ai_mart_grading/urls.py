from django.shortcuts import redirect
from django.urls import path

from . import views

app_name = "ai_mart_grading"

urlpatterns = [
    path("", lambda r: redirect("asset_intake:list")),
    path("assets/<int:pk>/assess/", views.run_assessment, name="run_assessment"),
]
