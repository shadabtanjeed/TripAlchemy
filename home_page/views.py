import random
import string
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import firebase_admin
from firebase_admin import auth
from functools import wraps
from django.conf import settings
import pandas as pd
import os
import google.generativeai as genai
from django.contrib.auth.decorators import login_required
import requests
import re
import openmeteo_requests
import requests_cache
from retry_requests import retry
from django.views.decorators.http import require_POST
from datetime import datetime
from datetime import timedelta
import PyCurrency_Converter
from forex_python.converter import CurrencyRates, RatesNotAvailableError
from firebase_admin import firestore


# Custom decorator to verify Firebase ID token
def firebase_auth_required(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        id_token = request.COOKIES.get("firebaseToken")

        if not id_token:
            return redirect("/user_authentication/login/")

        try:
            # Verify the ID token
            decoded_token = auth.verify_id_token(id_token)
            request.user_id = decoded_token["uid"]
            return view_func(request, *args, **kwargs)
        except Exception as e:
            return redirect("/user_authentication/login/")

    return wrapped_view


@firebase_auth_required
def index(request):
    username = request.GET.get("username")
    if not username:
        return redirect("/user_authentication/login/")

    # Store username in session
    request.session["username"] = username
    return render(
        request,
        "home_page.html",
        {"username": username, "firebase_config": settings.FIREBASE_CONFIG},
    )


def get_city_suggestions(request):
    query = request.GET.get("query", "").lower()

    if not query:
        return JsonResponse({"suggestions": []})

    try:
        csv_path = os.path.join(
            settings.BASE_DIR, "home_page", "static", "worldcities.csv"
        )

        df = pd.read_csv(csv_path, encoding="utf-8")
        mask = df["city"].str.lower().str.startswith(query)

        results = (
            df[mask]
            .apply(
                lambda row: {
                    "display": f"{row['city_ascii']}, {row['country']}",
                    "city": row["city_ascii"],
                    "country": row["country"],
                    "full": f"{row['city_ascii']}, {row['country']}",  # Added this field
                },
                axis=1,
            )
            .tolist()[:10]
        )

        return JsonResponse({"suggestions": results})
    except Exception as e:
        print(f"Debug: Error occurred: {str(e)}")
        return JsonResponse({"error": str(e)})


def get_airport_codes(request):
    source_city = request.GET.get("source")
    dest_city = request.GET.get("destination")

    if not source_city or not dest_city:
        return JsonResponse(
            {"error": "Missing source or destination city parameters"}, status=400
        )

    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-1.5-pro")

        prompt = f"""
        What are the main international airport codes for {source_city} and {dest_city}? 
        Use the most used/popular airport if multiple exists.
        If there is no airport in that city, name the airport closest to it.
        If source and destination in the same country, you should use local airports.
        If no airport found, simply return error and nothing else

        Use the following format:

        source: xxx
        destination: yyy
        
        Example:
        source: LAX
        destination: JFK

        Give nothing else but the airport codes.

        """

        result = model.generate_content(prompt)

        # Parse the response to extract airport codes
        lines = result.text.strip().split("\n")
        source_code = lines[0].split(": ")[1].strip()
        dest_code = lines[1].split(": ")[1].strip()

        return JsonResponse(
            {"result": {"source": source_code, "destination": dest_code}}
        )

    except Exception as e:
        print(f"Error getting airport codes: {e}")
        return JsonResponse({"error": "Failed to get airport codes"}, status=500)


@firebase_auth_required
def flight_page(request):
    # Store travel details in session
    request.session["travel_details"] = {
        "source": request.GET.get("source", ""),
        "destination": request.GET.get("destination", ""),
        "source_code": request.GET.get("source_code", ""),
        "dest_code": request.GET.get("dest_code", ""),
        "travel_date": request.GET.get("travel_date", ""),
        "return_date": request.GET.get("return_date", ""),
        "passengers": request.GET.get("passengers", ""),
        "budget": request.GET.get("budget", ""),
    }

    context = {
        **request.session["travel_details"],
        "firebase_config": settings.FIREBASE_CONFIG,
    }
    return render(request, "select_flight.html", context)


def get_flight_data(request):
    # Get parameters from request
    from_id = request.GET.get("from_id")
    to_id = request.GET.get("to_id")
    departure_date = request.GET.get("departure_date")
    return_date = request.GET.get("return_date")
    budget = request.GET.get("budget", "low")  # Default to low budget
    adults = request.GET.get("adults", 1)
    page = request.GET.get("page", 1)

    # make budget lowercase
    budget = budget.lower()

    # Set parameters based on budget preference
    if budget == "low":
        cabin_class = "ECONOMY"
        numberOfStops = "all"  # Default - allows all flights
    elif budget == "medium":
        cabin_class = "ECONOMY"
        numberOfStops = "nonstop_flights"  # Only direct flights
    else:  # high budget
        cabin_class = "BUSINESS"
        numberOfStops = "nonstop_flights"  # Only direct flights

    # Validate required parameters
    if not all([from_id, to_id, departure_date, return_date]):
        return JsonResponse(
            {
                "error": "Missing required parameters. Please provide from_id, to_id, departure_date, and return_date"
            },
            status=400,
        )

    url = "https://booking-com18.p.rapidapi.com/flights/search-return"

    querystring = {
        "fromId": from_id,
        "toId": to_id,
        "departureDate": departure_date,
        "returnDate": return_date,
        "cabinClass": cabin_class,
        "adults": adults,
        "page": page,
        "numberOfStops": numberOfStops,
    }

    headers = {
        "x-rapidapi-key": os.getenv("RAPID_API_BOOKING_KEY"),
        "x-rapidapi-host": "booking-com18.p.rapidapi.com",
    }

    response = requests.get(url, headers=headers, params=querystring)
    data = response.json()

    # Process response into simplified format
    try:
        simplified_data = {
            "total_flights_found": data["data"]["filteredFlightsCount"],
            "current_page": int(page),
            "total_pages": (data["data"]["filteredFlightsCount"] + 9)
            // 10,  # Ceiling division by 10
            "flights": [],
        }

        for flight in data["data"]["flights"]:
            # Get airline codes
            outbound_airline_code = flight["bounds"][0]["segments"][0][
                "marketingCarrier"
            ]["code"]
            inbound_airline_code = flight["bounds"][1]["segments"][0][
                "marketingCarrier"
            ]["code"]

            flight_info = {
                "id": flight["id"],
                "outbound": {
                    "flight_number": flight["bounds"][0]["segments"][0]["flightNumber"],
                    "airline": {
                        "code": outbound_airline_code,
                        "name": flight["bounds"][0]["segments"][0]["marketingCarrier"][
                            "name"
                        ],
                        "logo_url": f"https://images.kiwi.com/airlines/64/{outbound_airline_code}.png",
                    },
                    "origin": {
                        "code": flight["bounds"][0]["segments"][0]["origin"][
                            "airportCode"
                        ],
                        "city": flight["bounds"][0]["segments"][0]["origin"][
                            "cityName"
                        ],
                    },
                    "destination": {
                        "code": flight["bounds"][0]["segments"][0]["destination"][
                            "airportCode"
                        ],
                        "city": flight["bounds"][0]["segments"][0]["destination"][
                            "cityName"
                        ],
                    },
                    "departure": flight["bounds"][0]["segments"][0]["departuredAt"],
                    "arrival": flight["bounds"][0]["segments"][0]["arrivedAt"],
                },
                "inbound": {
                    "flight_number": flight["bounds"][1]["segments"][0]["flightNumber"],
                    "airline": {
                        "code": inbound_airline_code,
                        "name": flight["bounds"][1]["segments"][0]["marketingCarrier"][
                            "name"
                        ],
                        "logo_url": f"https://images.kiwi.com/airlines/64/{inbound_airline_code}.png",
                    },
                    "origin": {
                        "code": flight["bounds"][1]["segments"][0]["origin"][
                            "airportCode"
                        ],
                        "city": flight["bounds"][1]["segments"][0]["origin"][
                            "cityName"
                        ],
                    },
                    "destination": {
                        "code": flight["bounds"][1]["segments"][0]["destination"][
                            "airportCode"
                        ],
                        "city": flight["bounds"][1]["segments"][0]["destination"][
                            "cityName"
                        ],
                    },
                    "departure": flight["bounds"][1]["segments"][0]["departuredAt"],
                    "arrival": flight["bounds"][1]["segments"][0]["arrivedAt"],
                },
                "price": {
                    "amount": flight["travelerPrices"][0]["price"]["price"]["value"],
                    "currency": flight["travelerPrices"][0]["price"]["price"][
                        "currency"
                    ]["code"],
                    "vat": flight["travelerPrices"][0]["price"]["vat"]["value"],
                },
                "shareable_url": flight["shareableUrl"],
            }
            simplified_data["flights"].append(flight_info)

        return JsonResponse(simplified_data)

    except Exception as e:
        print(f"Error processing flight data: {str(e)}")
        return JsonResponse({"error": "Failed to process flight data"}, status=500)


@csrf_exempt
def clear_session(request):
    if request.method == "POST":
        request.session.flush()
        return JsonResponse({"status": "success"})
    return JsonResponse({"status": "error"}, status=405)


# Update hotel_page view in views.py
def hotel_page(request):
    # Get travel details from session
    travel_details = request.session.get("travel_details", {})
    flight_details = request.session.get("flight_details", {})

    context = {
        "destination": travel_details.get("destination", ""),
        "check_in": travel_details.get("travel_date", ""),
        "check_out": travel_details.get("return_date", ""),
        "guests": travel_details.get("passengers", ""),
        "firebase_config": settings.FIREBASE_CONFIG,
    }
    return render(request, "hotel_page.html", context)


# Add new view in views.py
@csrf_exempt
def store_flight_details(request):
    if request.method == "POST":
        data = json.loads(request.body)

        # Store flight details in session
        request.session["flight_details"] = {
            "outbound_airline": data["outbound_airline"],
            "outbound_flight_no": data["outbound_flight"],
            "inbound_airline": data["inbound_airline"],
            "inbound_flight_no": data["inbound_flight"],
            "total_price": data["total_price"],
            "currency": data["currency"],
        }

        # print the details stored in session

        print(request.session["flight_details"])

        return JsonResponse({"status": "success"})
    return JsonResponse({"status": "error"}, status=405)


# get location_id for destination city
@csrf_exempt
def get_location_id(request):
    city = request.GET.get("city")
    if not city:
        return JsonResponse({"error": "Missing city parameter"}, status=400)

    url = "https://booking-com18.p.rapidapi.com/stays/auto-complete"
    querystring = {"query": city}
    headers = {
        "x-rapidapi-key": os.getenv("RAPID_API_BOOKING_KEY"),
        "x-rapidapi-host": "booking-com18.p.rapidapi.com",
    }

    try:
        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status()
        data = response.json()

        # Find city object and extract ID
        for location in data.get("data", []):
            if location.get("dest_type") == "city":
                return JsonResponse({"city_id": location.get("id")})

        return JsonResponse({"error": "City not found"}, status=404)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# get hotel list from city_id
def get_hotel_list(request):
    location_id = request.GET.get("city_id")
    checkinDate = request.GET.get("checkinDate")
    checkoutDate = request.GET.get("checkoutDate")
    adults = request.GET.get("adults")
    page = request.GET.get("page", "1")

    url = "https://booking-com18.p.rapidapi.com/stays/search"
    querystring = {
        "locationId": location_id,
        "checkinDate": checkinDate,
        "checkoutDate": checkoutDate,
        "adults": adults,
        "sortBy": "price",
        "page": page,
        "units": "metric",
        "temperature": "c",
    }

    headers = {
        "x-rapidapi-key": os.getenv("RAPID_API_BOOKING_KEY"),
        "x-rapidapi-host": "booking-com18.p.rapidapi.com",
    }

    try:
        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status()
        data = response.json()

        total_pages = data.get("meta", {}).get("totalPages", 1)
        current_page = int(page)

        simplified_hotels = []
        for hotel in data.get("data", []):
            simplified_hotel = {
                "hotel_id": hotel.get("id"),
                "hotel_name": hotel.get("name"),
                "hotel_price": {
                    "amount": hotel.get("priceBreakdown", {})
                    .get("grossPrice", {})
                    .get("value"),
                    "currency": hotel.get("currency"),
                },
                "hotel_photo_url": (
                    hotel.get("photoUrls", [])[0] if hotel.get("photoUrls") else None
                ),
                "hotel_review_score": hotel.get("reviewScore"),
                "checkin": hotel.get("checkin", {}),
                "checkout": hotel.get("checkout", {}),
            }
            simplified_hotels.append(simplified_hotel)

        return JsonResponse(
            {
                "status": "success",
                "hotels": simplified_hotels,
                "pagination": {
                    "current_page": current_page,
                    "total_pages": total_pages,
                },
            }
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# get hotel details from hotel_id
def get_hotel_details(request):
    hotel_id = request.GET.get("hotel_id")
    checkinDate = request.GET.get("checkinDate")
    checkoutDate = request.GET.get("checkoutDate")

    url = "https://booking-com18.p.rapidapi.com/stays/detail"

    querystring = {
        "hotelId": hotel_id,
        "checkinDate": checkinDate,
        "checkoutDate": checkoutDate,
        "units": "metric",
    }

    headers = {
        "x-rapidapi-key": os.getenv("RAPID_API_BOOKING_KEY"),
        "x-rapidapi-host": "booking-com18.p.rapidapi.com",
    }

    try:
        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status()
        data = response.json()

        simplified_data = {
            "hotel_url": data.get("data", {}).get("url"),
            "hotel_address": data.get("data", {}).get("address"),
        }

        return JsonResponse({"status": "success", "hotel_details": simplified_data})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def get_hotels_from_city(request):
    try:

        # Get travel details from session

        travel_details = request.session.get("travel_details", {})
        city = travel_details.get("destination")
        check_in = travel_details.get("travel_date")
        check_out = travel_details.get("return_date")
        guests = travel_details.get("passengers", 1)
        budget = travel_details.get("budget", "low").lower()

        # Get parameters from URL

        # city = request.GET.get("city")
        # check_in = request.GET.get("check_in")
        # check_out = request.GET.get("check_out")
        # guests = request.GET.get("guests", "1")
        # budget = request.GET.get("budget", "low").lower()
        page = request.GET.get("page", "1")

        # Validate required parameters
        if not all([city, check_in, check_out]):
            return JsonResponse(
                {
                    "error": "Missing required parameters. Please provide city, check_in, and check_out"
                },
                status=400,
            )

        # Step 1: Get location ID
        location_response = requests.get(
            f"{request.build_absolute_uri('/')[:-1]}/home/get_location_id/",
            params={"city": city},
        )
        location_data = location_response.json()
        if "error" in location_data:
            return JsonResponse({"error": "City not found"}, status=404)

        city_id = location_data.get("city_id")

        # Step 2: Get hotel list
        hotel_list_response = requests.get(
            f"{request.build_absolute_uri('/')[:-1]}/home/get_hotel_list/",
            params={
                "city_id": city_id,
                "checkinDate": check_in,
                "checkoutDate": check_out,
                "adults": guests,
                "budget": budget,
                "page": page,
            },
        )
        hotel_list_data = hotel_list_response.json()

        # Process only 2 hotels per page
        hotels = []
        all_hotels = hotel_list_data.get("hotels", [])
        start_idx = (int(page) - 1) * 2
        end_idx = start_idx + 2

        # Step 3: Get details for each hotel in the page
        for hotel in all_hotels[start_idx:end_idx]:
            hotel_details_response = requests.get(
                f"{request.build_absolute_uri('/')[:-1]}/home/get_hotel_details/",
                params={
                    "hotel_id": hotel.get("hotel_id"),
                    "checkinDate": check_in,
                    "checkoutDate": check_out,
                },
            )
            hotel_details = hotel_details_response.json()

            # Combine hotel info with details
            hotel_info = {
                "hotel_id": hotel.get("hotel_id"),
                "hotel_name": hotel.get("hotel_name"),
                "hotel_price": hotel.get("hotel_price"),
                "hotel_photo_url": hotel.get("hotel_photo_url"),
                "hotel_review_score": hotel.get("hotel_review_score"),
                "checkin": hotel.get("checkin"),
                "checkout": hotel.get("checkout"),
                "url": hotel_details.get("hotel_details", {}).get("hotel_url"),
                "address": hotel_details.get("hotel_details", {}).get("hotel_address"),
            }
            hotels.append(hotel_info)

        total_hotels = len(all_hotels)
        total_pages = (total_hotels + 2) // 3  # Ceiling division by 3

        return JsonResponse(
            {
                "status": "success",
                "hotels": hotels,
                "pagination": {"current_page": int(page), "total_pages": total_pages},
            }
        )

    except Exception as e:
        print(f"Error in get_hotels_from_city: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


def get_itinerary_data(request):

    # Get travel details from session

    travel_details = request.session.get("travel_details", {})
    city = travel_details.get("destination")
    source = travel_details.get("source")
    check_in = travel_details.get("travel_date")
    check_out = travel_details.get("return_date")
    guests = travel_details.get("passengers", 1)
    budget = travel_details.get("budget", "low").lower()

    # Get parameters from URL

    # city = request.GET.get("city")
    # source = request.GET.get("source")
    # check_in = request.GET.get("check_in")
    # check_out = request.GET.get("check_out")
    # guests = request.GET.get("guests", "1")
    # budget = request.GET.get("budget", "low").lower()

    # For testing purpose:
    # city = "Singapore"
    # source = "Dhaka"
    # check_in = "2024-12-25"
    # check_out = "2025-01-03"
    # guests = "4"
    # budget = "low"

    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-1.5-pro")

        prompt = f"""
        

        Provide me a itinerary for a trip to {city} for {guests} guests with a {budget} budget. 
        The trip is from {check_in} to {check_out}.
        The guests are from the city of {source}.
        The hotel fare, plane fare are already calculated before. Do not consider them. But do consider the meal costs.
        The trip should include visitng local and popular tourist attractions, dining at local restaurants, and shopping at local markets and much more. If there is any special occassion/event during that time at that location, do consider that as well. Like christam or new year or any festival.
        But do consider the budget and the number of days of the trip.
        For low budget, you can consider they are students, for medium budget they are family, and for high budget they are business people.4
        For each of the activity, mention the approximate cost per person for that activity.
        Do not use words like luxury hotel, cheap hotel, expensive hotel, or resturants. Just mention the name of the place.

        In separate parts, you should mention the approximate cost per person for the whole trip as well as all the locations mentioned. For mentioning location, you do not need to mention the local places and restaurants which does not have a specific name.

        Use the following format:

        Header: x days itinerary in {city} for {guests} guests.
        Day 1:
            Morning:
            Afternoon:
            Evening:
            Night:
            Approximate cost per person: 
        Day 2:
            Morning:
            Afternoon:
            Evening:
            Night:
            Approximate cost per person:
        .....
        
        Total cost (per person): xxx USD

        Mentioned Locations
            1. Location 1
            2. Location 2 
            3. Location 3
            ....

        Example:

        Header: 3 days itinerary in Paris for 2 guests.
        Day 1:
            Morning: Visit Eiffel Tower
            Afternoon: Lunch at local cafe
            Evening: Visit Louvre Museum
            Night: Dinner at local restaurant
            Approximate cost per person: 100 USD
        Day 2:
            Morning: Visit Notre Dame Cathedral
            Afternoon: Lunch at local cafe
            Evening: Shopping at local market
            Night: Dinner at local restaurant
            Approximate cost per person: 150 USD
        Day 3:
            Morning: Visit Palace of Versailles
            Afternoon: Lunch at local cafe
            Evening: Visit Montmartre
            Night: Dinner at local restaurant
            Approximate cost per person: 200 USD
        
        Total cost (per person): 450 USD

        Mentioned Locations
            1. Eiffel Tower
            2. Louvre Museum
            3. Notre Dame Cathedral
            4. Palace of Versailles
            5. Montmartre
        

        Give nothing else apart from the itinerary in the above format.You must add header. 
        Do not add anything extra in total costs. Just mention the total cost. like 100 USD or 200 USD. Do not add currency symbol at the end/front of the total cost. 
        Same thing goes for mentioned location. For mentioned location, do not mention anything that has no specific name like local market or local restaurant.

        """

        result = model.generate_content(prompt)
        itinerary_text = result.text

        # Parse the generated text into structured JSON
        itinerary = parse_itinerary(itinerary_text)

        # store the mentioned locations in session
        mentioned_locations = itinerary.get("mentioned_locations", [])

        # Remove numbering from each location
        cleaned_locations = [
            re.sub(r"^\d+\.\s*", "", loc) for loc in mentioned_locations
        ]

        # Store cleaned locations in session
        request.session["mentioned_locations"] = cleaned_locations

        print(f"Cleaned mentioned locations: {request.session['mentioned_locations']}")

        return {"status": "success", "itinerary": itinerary}

    except Exception as e:
        print(f"Error getting itinerary: {e}")
        return {"status": "error", "message": "Failed to get itinerary"}


def parse_itinerary(itinerary_text):
    itinerary = {}
    days = []
    locations = []

    # Extract header
    header_match = re.search(r"Header: (.+)", itinerary_text)
    if header_match:
        itinerary["header"] = header_match.group(1)

    # Extract days
    day_matches = re.findall(
        r"Day \d+:(.+?)(?=Day \d+:|Total cost)", itinerary_text, re.DOTALL
    )
    for day_match in day_matches:
        day = {}
        day_parts = re.findall(
            r"(Morning|Afternoon|Evening|Night):(.+?)(?=(Morning|Afternoon|Evening|Night|Approximate cost))",
            day_match,
            re.DOTALL,
        )
        for part in day_parts:
            day[part[0].strip()] = part[1].strip()
        cost_match = re.search(r"Approximate cost per person: (.+)", day_match)
        if cost_match:
            day["Approximate cost per person"] = cost_match.group(1).strip()
        days.append(day)

    itinerary["days"] = days

    # Extract total cost
    total_cost_match = re.search(r"Total cost \(per person\): (.+)", itinerary_text)
    if total_cost_match:
        itinerary["total_cost_per_person"] = total_cost_match.group(1).strip()

    # Extract mentioned locations
    locations_match = re.search(r"Mentioned Locations(.+)", itinerary_text, re.DOTALL)
    if locations_match:
        locations = [
            loc.strip()
            for loc in locations_match.group(1).strip().split("\n")
            if loc.strip()
        ]
    itinerary["mentioned_locations"] = locations

    return itinerary


def itinerary_page(request):
    itinerary_data = get_itinerary_data(request)

    if itinerary_data["status"] == "success":

        google_api_key = os.getenv("GOOGLE_MAP_API_KEY")

        # Call the get_geocoding_from_place function and extract the JSON content
        geocoding_response = get_geocoding_from_place(request)

        # Parse the JsonResponse content
        geocoding_data = json.loads(geocoding_response.content)

        # Check if there is an error
        if geocoding_data.get("error"):
            # Handle the error case
            print(f"Error getting geocoding data: {geocoding_data['error']}")
            return JsonResponse(
                geocoding_data, status=geocoding_data.get("status", 500)
            )

        # Get the geocoding results
        geocoding_results = geocoding_data.get("results", [])

        # Log the geocoding results for debugging
        # print("Geocoding results:", geocoding_results)
        context = {
            "itinerary": itinerary_data["itinerary"],
            "firebase_config": settings.FIREBASE_CONFIG,
            "google_api_key": google_api_key,
            "geocoding_results": json.dumps(geocoding_results),
        }
    else:
        context = {
            "error": itinerary_data["message"],
            "firebase_config": settings.FIREBASE_CONFIG,
        }
    return render(request, "itinerary_page.html", context)


@csrf_exempt
def store_hotel_details(request):
    if request.method == "POST":
        data = json.loads(request.body)

        # Store hotel details in session
        request.session["hotel_details"] = {
            "hotel_name": data["hotel_name"],
            "hotel_price": data["hotel_price"],
            "hotel_currency": data["hotel_currency"],
        }

        # print session data
        print(request.session["hotel_details"])

        return JsonResponse({"status": "success"})

    return JsonResponse({"status": "error"}, status=405)


@csrf_exempt
def get_itinerary_data_view(request):
    try:
        data = get_itinerary_data(request)

        if data["status"] == "success":
            itinerary = data["itinerary"]

            # print(f"Generated itinerary: {itinerary}")

            mentioned_locations = itinerary.get("mentioned_locations", [])

            # Store mentioned locations in session
            request.session["mentioned_locations"] = mentioned_locations

            # print(f"Mentioned locations: {mentioned_locations}")

            return JsonResponse(data)
        else:
            return JsonResponse(data, status=500)
    except Exception as e:
        error_data = {"status": "error", "message": str(e)}
        return JsonResponse(error_data, status=500)


@csrf_exempt
def get_geocoding_from_place(request):
    # Retrieve mentioned locations from session
    mentioned_locations = request.session.get("mentioned_locations", [])

    if not mentioned_locations:
        return JsonResponse(
            {"error": "No mentioned locations found in session"}, status=400
        )

    google_api_key = os.getenv("GOOGLE_MAP_API_KEY")
    if not google_api_key:
        return JsonResponse({"error": "Missing Google Maps API key"}, status=500)

    endpoint = "https://maps.googleapis.com/maps/api/geocode/json"
    geocoding_results = []

    for place in mentioned_locations:
        params = {"address": place, "key": google_api_key}

        try:
            response = requests.get(endpoint, params=params)
            response.raise_for_status()  # Raise an exception for HTTP errors
            data = response.json()
            geocoding_results.append({"place": place, "geocoding_data": data})
        except requests.RequestException as e:
            geocoding_results.append({"place": place, "error": str(e)})

    return JsonResponse({"results": geocoding_results})


def map_page(request):
    google_api_key = os.getenv("GOOGLE_MAP_API_KEY")

    # Call the get_geocoding_from_place function and extract the JSON content
    geocoding_response = get_geocoding_from_place(request)

    # Parse the JsonResponse content
    geocoding_data = json.loads(geocoding_response.content)

    # Check if there is an error
    if geocoding_data.get("error"):
        # Handle the error case
        print(f"Error getting geocoding data: {geocoding_data['error']}")
        return JsonResponse(geocoding_data, status=geocoding_data.get("status", 500))

    # Get the geocoding results
    geocoding_results = geocoding_data.get("results", [])

    # Log the geocoding results for debugging
    print("Geocoding results:", geocoding_results)

    context = {
        "firebase_config": settings.FIREBASE_CONFIG,
        "google_api_key": google_api_key,
        "geocoding_results": json.dumps(geocoding_results),
    }

    return render(request, "map_page.html", context)


def get_weather_data(request):
    user_latitude = request.session.get("latitude")
    user_longitude = request.session.get("longitude")

    # print the latitude and longitude
    print(f"Latitude: {user_latitude}, Longitude: {user_longitude}")

    travel_details = request.session.get("travel_details", {})
    check_in_raw = travel_details.get("travel_date")
    check_out_raw = travel_details.get("return_date")

    # check if checkin is within 14 days from current date or not
    checkin_date = datetime.strptime(check_in_raw, "%Y-%m-%d")
    current_date = datetime.now()
    days_until_checkin = (checkin_date - current_date).days

    if days_until_checkin < 0 or days_until_checkin > 14:
        return JsonResponse(
            {"error": "Check-in date should be within 14 days from the current date."},
            status=400,
        )

    # Check if checkout is within 14 days from current date or not
    checkout_date = datetime.strptime(check_out_raw, "%Y-%m-%d")
    days_until_checkout = (checkout_date - current_date).days

    if days_until_checkout < 0 or days_until_checkout > 14:
        print("Checkout date is not within 14 days from the current date.")
        # Set checkout to exactly 13 days after check-in
        checkout_date = current_date + timedelta(days=14)
        check_out_raw = checkout_date.strftime("%Y-%m-%d")

    # Now print the checkin and checkout dates after possible modification
    print(f"Check-in: {check_in_raw}, Check-out: {check_out_raw}")

    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession(".cache", expire_after=3600)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    # Make sure all required weather variables are listed here
    # The order of variables in hourly or daily is important to assign them correctly below
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": user_latitude,
        "longitude": user_longitude,
        "daily": [
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "apparent_temperature_max",
            "apparent_temperature_min",
            "uv_index_max",
            "rain_sum",
            "showers_sum",
            "snowfall_sum",
        ],
        "timezone": "auto",
        "start_date": check_in_raw,
        "end_date": check_out_raw,
    }
    responses = openmeteo.weather_api(url, params=params)

    # Process first location. Add a for-loop for multiple locations or weather models
    response = responses[0]
    print(f"Coordinates {response.Latitude()}°N {response.Longitude()}°E")
    print(f"Elevation {response.Elevation()} m asl")
    print(f"Timezone {response.Timezone()} {response.TimezoneAbbreviation()}")
    print(f"Timezone difference to GMT+0 {response.UtcOffsetSeconds()} s")

    # Process daily data. The order of variables needs to be the same as requested.
    daily = response.Daily()
    daily_weather_code = daily.Variables(0).ValuesAsNumpy()
    daily_temperature_2m_max = daily.Variables(1).ValuesAsNumpy()
    daily_temperature_2m_min = daily.Variables(2).ValuesAsNumpy()
    daily_apparent_temperature_max = daily.Variables(3).ValuesAsNumpy()
    daily_apparent_temperature_min = daily.Variables(4).ValuesAsNumpy()
    daily_uv_index_max = daily.Variables(5).ValuesAsNumpy()
    daily_rain_sum = daily.Variables(6).ValuesAsNumpy()
    daily_showers_sum = daily.Variables(7).ValuesAsNumpy()
    daily_snowfall_sum = daily.Variables(8).ValuesAsNumpy()

    daily_data = {
        "date": pd.date_range(
            start=pd.to_datetime(daily.Time(), unit="s", utc=True),
            end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=daily.Interval()),
            inclusive="left",
        )
    }
    daily_data["weather_code"] = daily_weather_code
    daily_data["temperature_2m_max"] = daily_temperature_2m_max
    daily_data["temperature_2m_min"] = daily_temperature_2m_min
    daily_data["apparent_temperature_max"] = daily_apparent_temperature_max
    daily_data["apparent_temperature_min"] = daily_apparent_temperature_min
    daily_data["uv_index_max"] = daily_uv_index_max
    daily_data["rain_sum"] = daily_rain_sum
    daily_data["showers_sum"] = daily_showers_sum
    daily_data["snowfall_sum"] = daily_snowfall_sum

    daily_dataframe = pd.DataFrame(data=daily_data)

    # Convert timestamp to readable date and create a structured response
    daily_dataframe["date"] = pd.to_datetime(
        daily_dataframe["date"], unit="ms"
    ).dt.strftime("%Y-%m-%d")

    # Map weather codes to human-readable descriptions
    weather_code_map = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow fall",
        73: "Moderate snow fall",
        75: "Heavy snow fall",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with light hail",
        99: "Thunderstorm with heavy hail",
    }

    # Prepare structured response
    weather_data = []
    for _, row in daily_dataframe.iterrows():
        weather_data.append(
            {
                "date": row["date"],
                "weather": {
                    "code": int(row["weather_code"]),
                    "description": weather_code_map.get(
                        int(row["weather_code"]), "Unknown"
                    ),
                },
                "temperature": {
                    "max": round(row["temperature_2m_max"], 1),
                    "min": round(row["temperature_2m_min"], 1),
                    "apparent_max": round(row["apparent_temperature_max"], 1),
                    "apparent_min": round(row["apparent_temperature_min"], 1),
                },
                "uv_index": round(row["uv_index_max"], 1),
                "precipitation": {
                    "rain": round(row["rain_sum"], 1),
                    "showers": round(row["showers_sum"], 1),
                    "snowfall": round(row["snowfall_sum"], 1),
                },
            }
        )

    # Return the structured response
    return JsonResponse(
        {
            "status": "success",
            "location": {"latitude": user_latitude, "longitude": user_longitude},
            "travel_dates": {"check_in": check_in_raw, "check_out": check_out_raw},
            "weather_forecast": weather_data,
        }
    )


def get_session_data(request):
    # Define keys to exclude from the response
    exclude_keys = {"_auth_user_id", "session_key", "csrf_token"}

    # Retrieve all session data
    session_data = {
        key: value for key, value in request.session.items() if key not in exclude_keys
    }

    return JsonResponse(session_data)


@csrf_exempt
def store_itinerary_cost(request):
    try:
        data = json.loads(request.body)
        itinerary_cost = data.get("itinerary_cost", None)
        latitude = data.get("latitude", None)
        longitude = data.get("longitude", None)

        if itinerary_cost is None or latitude is None or longitude is None:
            return JsonResponse({"error": "Required data not provided."}, status=400)

        # Convert to float or int as needed
        try:
            itinerary_cost_value = float(itinerary_cost)
            latitude_value = float(latitude)
            longitude_value = float(longitude)
        except ValueError:
            return JsonResponse({"error": "Invalid data format."}, status=400)

        # Store in session
        request.session["itinerary_cost"] = itinerary_cost_value
        request.session["latitude"] = latitude_value
        request.session["longitude"] = longitude_value

        return JsonResponse(
            {
                "success": True,
                "itinerary_cost": itinerary_cost_value,
                "latitude": latitude_value,
                "longitude": longitude_value,
            },
            status=200,
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def weather_page(request):
    # call get_weather_data function
    weather_data = get_weather_data(request)

    # parse the JsonResponse content
    weather_data = json.loads(weather_data.content)

    # Check if there is an error
    if weather_data.get("error"):
        # Handle the error case
        print(f"Error getting weather data: {weather_data['error']}")
        return JsonResponse(weather_data, status=weather_data.get("status", 500))

    # Get the weather results

    weather_results = weather_data.get("weather_forecast", [])

    # get the destination city and travel dates

    travel_details = request.session.get("travel_details", {})
    destination = travel_details.get("destination")
    check_in = travel_details.get("travel_date")
    check_out = travel_details.get("return_date")

    context = {
        "firebase_config": settings.FIREBASE_CONFIG,
        "weather_results": json.dumps(weather_results),
        "destination": destination,
        "check_in": check_in,
        "check_out": check_out,
    }

    return render(request, "weather_page.html", context)


import requests


def trip_summary_page(request):

    # get travel details
    travel_details = request.session.get("travel_details", {})
    source = travel_details.get("source")
    destination = travel_details.get("destination")
    travel_date = travel_details.get("travel_date")
    return_date = travel_details.get("return_date")
    passengers = travel_details.get("passengers")
    budget = travel_details.get("budget")

    # get flight details
    flight_details = request.session.get("flight_details", {})
    outbound_airline = flight_details.get("outbound_airline")
    outbound_flight_no = flight_details.get("outbound_flight_no")
    inbound_airline = flight_details.get("inbound_airline")
    inbound_flight_no = flight_details.get("inbound_flight_no")
    flight_cost = flight_details.get("total_price")

    # get hotel details
    hotel_details = request.session.get("hotel_details", {})
    hotel_name = hotel_details.get("hotel_name")
    hotel_price = hotel_details.get("hotel_price")
    hotel_currency = hotel_details.get("hotel_currency")

    # get itinerary cost
    itinerary_cost = request.session.get("itinerary_cost")

    # Convert hotel price to USD if necessary
    if hotel_currency.lower() != "usd":
        hotel_currency = hotel_currency.upper()
        to_currency = "USD"

        try:
            url = (
                "https://currency-conversion-and-exchange-rates.p.rapidapi.com/convert"
            )
            querystring = {
                "from": hotel_currency,
                "to": to_currency,
                "amount": hotel_price,
            }
            headers = {
                "x-rapidapi-key": os.getenv("RAPID_API_BOOKING_KEY"),
                "x-rapidapi-host": "currency-conversion-and-exchange-rates.p.rapidapi.com",
            }

            response = requests.get(url, headers=headers, params=querystring)
            response_data = response.json()

            if "result" in response_data:
                hotel_price = response_data["result"]
                hotel_currency = to_currency
            else:
                return JsonResponse(
                    {
                        "error": "Currency conversion failed: 'result' key not found in response"
                    },
                    status=500,
                )

        except Exception as e:
            print(f"Error converting currency: {str(e)}")
            return JsonResponse(
                {"error": f"Failed to convert currency: {str(e)}"}, status=500
            )

    # print the type of the variable flight_cost
    print(f"Type of flight_cost: {type(flight_cost)}")

    # convert int to string
    flight_cost = str(flight_cost)

    # Convert flight_cost to float by inserting a decimal point before the last two characters

    if isinstance(flight_cost, str):
        # Remove any existing decimal points or commas
        flight_cost = flight_cost.replace(".", "").replace(",", "")

        # Ensure the string is long enough to have decimal places
        if len(flight_cost) > 2:
            flight_cost = float(flight_cost[:-2] + "." + flight_cost[-2:])
        elif len(flight_cost) == 2:
            flight_cost = float("0." + flight_cost)
        else:
            flight_cost = float(flight_cost)

    # Convert other costs to float
    hotel_price = float(hotel_price)
    itinerary_cost = float(itinerary_cost)
    passengers = int(passengers)

    # calculate total cost
    total_flight_cost = flight_cost * passengers
    total_hotel_cost = hotel_price * 1
    total_itinerary_cost = itinerary_cost * passengers

    total_cost = total_flight_cost + total_hotel_cost + total_itinerary_cost

    # limit them to max two decimals

    flight_cost = round(flight_cost, 2)
    hotel_price = round(hotel_price, 2)
    itinerary_cost = round(itinerary_cost, 2)
    total_flight_cost = round(total_flight_cost, 2)
    total_hotel_cost = round(total_hotel_cost, 2)
    total_itinerary_cost = round(total_itinerary_cost, 2)
    total_cost = round(total_cost, 2)

    # store everything into json
    trip_summary = {
        "source": source,
        "destination": destination,
        "travel_date": travel_date,
        "return_date": return_date,
        "passengers": passengers,
        "budget": budget,
        "outbound_airline": outbound_airline,
        "outbound_flight_no": outbound_flight_no,
        "inbound_airline": inbound_airline,
        "inbound_flight_no": inbound_flight_no,
        "flight_cost": flight_cost,
        "hotel_name": hotel_name,
        "hotel_price": hotel_price,
        "hotel_currency": hotel_currency,
        "itinerary_cost": itinerary_cost,
        "total_flight_cost": total_flight_cost,
        "total_hotel_cost": total_hotel_cost,
        "total_itinerary_cost": total_itinerary_cost,
        "total_cost": total_cost,
    }

    context = {
        "firebase_config": settings.FIREBASE_CONFIG,
        "trip_summary": trip_summary,
    }

    return render(request, "trip_summary_page.html", context)


@csrf_exempt  # Add this decorator
def store_trip_into_firebase(request):
    if request.method == "POST":
        try:
            # Get username
            username = request.session.get("username")
            if not username:
                return JsonResponse({"error": "User not logged in"}, status=401)

            # Get travel details
            travel_details = request.session.get("travel_details", {})
            source = travel_details.get("source")
            destination = travel_details.get("destination")
            travel_date = travel_details.get("travel_date")
            return_date = travel_details.get("return_date")
            passengers = travel_details.get("passengers")
            budget = travel_details.get("budget")

            # Get flight details
            flight_details = request.session.get("flight_details", {})
            flight_cost = flight_details.get("total_price")

            # Get hotel details
            hotel_details = request.session.get("hotel_details", {})
            hotel_name = hotel_details.get("hotel_name")
            hotel_price = float(hotel_details.get("hotel_price", 0))
            total_hotel_cost = hotel_price

            # Get itinerary cost
            itinerary_cost = request.session.get("itinerary_cost")

            # convert int to string
            flight_cost = str(flight_cost)

            # Convert flight_cost to float by inserting a decimal point before the last two characters

            if isinstance(flight_cost, str):
                # Remove any existing decimal points or commas
                flight_cost = flight_cost.replace(".", "").replace(",", "")

                # Ensure the string is long enough to have decimal places
                if len(flight_cost) > 2:
                    flight_cost = float(flight_cost[:-2] + "." + flight_cost[-2:])
                elif len(flight_cost) == 2:
                    flight_cost = float("0." + flight_cost)
                else:
                    flight_cost = float(flight_cost)

            # Convert other costs to float
            hotel_price = float(hotel_price)
            itinerary_cost = float(itinerary_cost)
            passengers = int(passengers)

            # calculate total cost
            total_flight_cost = flight_cost * passengers
            total_hotel_cost = hotel_price * 1
            total_itinerary_cost = itinerary_cost * passengers

            total_cost = total_flight_cost + total_hotel_cost + total_itinerary_cost

            # limit them to max two decimals

            flight_cost = round(flight_cost, 2)
            hotel_price = round(hotel_price, 2)
            itinerary_cost = round(itinerary_cost, 2)
            total_flight_cost = round(total_flight_cost, 2)
            total_hotel_cost = round(total_hotel_cost, 2)
            total_itinerary_cost = round(total_itinerary_cost, 2)
            total_cost = round(total_cost, 2)

            # Generate a random trip ID
            trip_id = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=10)
            )

            # Get Firestore client
            db = firestore.client()

            # Create trip document
            trip_data = {
                "username": username,
                "source": source,
                "destination": destination,
                "travel_date": travel_date,
                "return_date": return_date,
                "passengers": passengers,
                "budget": budget,
                "total_flight_cost": total_flight_cost,
                "hotel_name": hotel_name,
                "total_hotel_cost": total_hotel_cost,
                "total_itinerary_cost": total_itinerary_cost,
                "total_cost": total_cost,
                "created_at": firestore.SERVER_TIMESTAMP,
                "trip_id": trip_id,
            }

            # Add trip document to Firestore
            db.collection("trips").document(trip_id).set(trip_data)

            return JsonResponse({"status": "success", "trip_id": trip_id})

        except Exception as e:
            print(f"Error storing trip: {str(e)}")  # For debugging
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)
