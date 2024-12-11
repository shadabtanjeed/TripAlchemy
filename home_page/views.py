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
def select_flight(request):
    # Get parameters from URL
    context = {
        "source": request.GET.get("source", ""),
        "destination": request.GET.get("destination", ""),
        "source_code": request.GET.get("source_code", ""),
        "dest_code": request.GET.get("dest_code", ""),
        "travel_date": request.GET.get("travel_date", ""),
        "return_date": request.GET.get("return_date", ""),
        "passengers": request.GET.get("passengers", ""),
        "budget": request.GET.get("budget", ""),
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
