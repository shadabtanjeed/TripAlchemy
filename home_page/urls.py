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
    path("hotel/", views.hotel_page, name="hotel_page"),
    path(
        "store_flight_details/", views.store_flight_details, name="store_flight_details"
    ),
    path("get_location_id/", views.get_location_id, name="get_location_id"),
    path("get_hotel_list/", views.get_hotel_list, name="get_hotel_list"),
    path("get_hotel_details/", views.get_hotel_details, name="get_hotel_details"),
    path(
        "get_hotels_from_city/", views.get_hotels_from_city, name="get_hotels_from_city"
    ),
    path(
        "get_itinerary_data/", views.get_itinerary_data_view, name="get_itinerary_data"
    ),
    path("parse_itinerary/", views.parse_itinerary, name="parse_itinerary"),
    path("itinerary/", views.itinerary_page, name="itinerary_page"),
    path("store_hotel_details/", views.store_hotel_details, name="store_hotel_details"),
    path(
        "get_geocoding_from_place/",
        views.get_geocoding_from_place,
        name="get_geocoding_from_place",
    ),
    path("map/", views.map_page, name="map_page"),
    path("get_weather_data/", views.get_weather_data, name="get_weather_data"),
    path("get_session_data/", views.get_session_data, name="get_session_data"),
    path(
        "store_itinerary_cost/", views.store_itinerary_cost, name="store_itinerary_cost"
    ),
    path("weather/", views.weather_page, name="weather_page"),
    path("trip_summary/", views.trip_summary_page, name="trip_summary_page"),
    path(
        "store_trip_into_firebase/",
        views.store_trip_into_firebase,
        name="store_trip_into_firebase",
    ),
]
