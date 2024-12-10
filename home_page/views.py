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
