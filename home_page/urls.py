from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "get_city_suggestions/", views.get_city_suggestions, name="get_city_suggestions"
    ),
    path("get_airport_codes/", views.get_airport_codes, name="get_airport_codes"),
    path("flight/", views.flight_page, name="select_flight"),
    path("get_flight_data/", views.get_flight_data, name="get_flight_data"),
    path("clear_session/", views.clear_session, name="clear_session"),
]
