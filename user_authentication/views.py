from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.db import connection
from django.db.utils import DatabaseError
import hashlib
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
import json
import firebase_admin
from firebase_admin import auth
from django.contrib import messages


def index(request):
    return render(request, "login_page.html")


def login_view(request):

    return render(request, "login_page.html")


@csrf_exempt
def signup_view(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            email = data["email"]
            password = data["password"]
            user = auth.create_user(email=email, password=password)
            return JsonResponse({"success": True, "user_id": user.uid})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})
    return render(request, "signup_page.html")
