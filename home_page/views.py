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
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
import json
import firebase_admin
from firebase_admin import auth
import requests
from django.conf import settings
import re


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

        # Process only 1 hotels per page
        hotels = []
        all_hotels = hotel_list_data.get("hotels", [])
        start_idx = (int(page) - 1) * 1
        end_idx = start_idx + 1

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
        model = genai.GenerativeModel("gemini-1.5-flash")

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
        

        Give nothing else apart from the itinerary in the above format.
        Do not add anything extra in total costs. Just mention the total cost. like 100 USD or 200 USD. Do not add currency symbol at the end/front of the total cost. 
        Same thing goes for mentioned location. For mentioned location, do not mention anything that has no specific name like local market or local restaurant.

        """

        result = model.generate_content(prompt)
        itinerary_text = result.text

        # Parse the generated text into structured JSON
        itinerary = parse_itinerary(itinerary_text)

        return JsonResponse({"status": "success", "itinerary": itinerary})

    except Exception as e:
        print(f"Error getting itinerary: {e}")
        return JsonResponse({"error": "Failed to get itinerary"}, status=500)


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
        itinerary["Total cost (per person)"] = total_cost_match.group(1).strip()

    # Extract mentioned locations
    locations_match = re.search(r"Mentioned Locations(.+)", itinerary_text, re.DOTALL)
    if locations_match:
        locations = [
            loc.strip()
            for loc in locations_match.group(1).strip().split("\n")
            if loc.strip()
        ]
    itinerary["Mentioned Locations"] = locations

    return itinerary
