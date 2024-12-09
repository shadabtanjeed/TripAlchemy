from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.db import connection
from django.db.utils import DatabaseError
import hashlib
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json


def index(request):
    return render(request, "login_page.html")


def login_view(request):

    return render(request, "login_page.html")


def signup_view(request):

    return render(request, "signup_page.html")
