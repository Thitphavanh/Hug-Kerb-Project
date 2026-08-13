from django.urls import path

from . import views

app_name = "digital_member"

urlpatterns = [
    path("", views.lookup, name="lookup"),
    path("t/<str:token>/", views.track_asset, name="track"),
    path("logout/<str:token>/", views.logout_portal, name="logout"),
    path("card/<str:card_number>/", views.member_card_view, name="member_card"),
    path(
        "card/<str:card_number>/image.png",
        views.member_card_image,
        name="member_card_image",
    ),
]
