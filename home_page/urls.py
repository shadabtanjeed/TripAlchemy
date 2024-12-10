from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "get_city_suggestions/", views.get_city_suggestions, name="get_city_suggestions"
    ),
]
