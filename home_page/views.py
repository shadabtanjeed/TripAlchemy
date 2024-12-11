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
