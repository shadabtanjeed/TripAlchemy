from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import firebase_admin
from firebase_admin import auth

from django.conf import settings


def index(request):
    return render(request, "login_page.html")


def login_view(request):

    return render(
        request, "login_page.html", {"firebase_config": settings.FIREBASE_CONFIG}
    )


@csrf_exempt
def signup_view(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            username = data["username"]
            password = data["password"]
            email = f"{username}@email.com"
            user = auth.create_user(email=email, password=password)
            return JsonResponse({"success": True, "user_id": user.uid})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})
    return render(request, "signup_page.html")
