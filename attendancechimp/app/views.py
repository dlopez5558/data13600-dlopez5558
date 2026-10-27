"""
views.py — HTTP request handlers for AttendanceChimp.

Each view corresponds to one URL endpoint.  Views receive an HTTP request,
interact with the database via models.py, and return an HTTP response.
"""

from django.shortcuts import render, redirect
from django.http import (HttpResponse, HttpResponseForbidden,
                         HttpResponseBadRequest, JsonResponse)
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login
from datetime import datetime
import zoneinfo
import json
import io

# from .models import (InstructorProfile, StudentProfile, Course, Enrollment,
#                      Lecture, QRCodeUpload, is_instructor, is_student,
#                      getUploadsForCourse)

CDT = zoneinfo.ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# HW2  — index, time, sum
# ---------------------------------------------------------------------------

from datetime import datetime
from zoneinfo import ZoneInfo

def index(request):
    """Render the home page (index.html)."""
    context = {}
    return render(request, 'app/index.html', context)


def time_view(request):
    now = datetime.now(ZoneInfo("America/Chicago"))
    return HttpResponse(now.strftime("%H:%M"), content_type="text/plain")


def sum_view(request):
    return HttpResponse(f"<p>{float(request.GET.get('n1')) + float(request.GET.get('n2'))}</p>"
    )


# ---------------------------------------------------------------------------
# HW4  — user creation
# ---------------------------------------------------------------------------

from .models import Student_Profile, Instructor_Profile

def index(request):
    """
    Render the home page with the current Central time and user.
    """
    now = datetime.now(ZoneInfo("America/Chicago"))
    context = {
        "current_time": now.strftime("%H:%M"),
        "user": request.user,
        
    }
    return render(request, "app/index.html", context)


def signup_view(request):
    '''
    Shows the signup form. Only accepts Get requests.
    '''
    if request.method != "GET":
        return HttpResponseBadRequest("Only GET requests are allowed.")

    return render(request, "app/new.html")

@csrf_exempt
def createUser(request):
    '''
    Create a user based on user response and database
    '''
    if request.method != "POST":
        return HttpResponseBadRequest("Only POST requests are allowed.")
    
    email = request.POST.get("email")
    user_name = request.POST.get("user_name")
    password = request.POST.get("password")
    is_student = request.POST.get("is_student")

    # My schema from models.py has some requirements on lengths of names.
    # This code here is to make failure to satisfy those requirements transparent
    # to the user.

    if not email or not user_name or not password:
        return HttpResponseBadRequest(
            "Email, username, and password are required."
        )

    if len(user_name) > 20:
        return HttpResponseBadRequest(
            "Username must be 20 characters or fewer."
        )

    if is_student not in ("0", "1"):
        return HttpResponseBadRequest(
            "Select student or instructor."
        )

    if User.objects.filter(username=user_name).exists():
        return HttpResponseBadRequest(
            "This username is already taken."
        )

    if User.objects.filter(email=email).exists():
        return HttpResponseBadRequest("An account with this email already exists.")

    
    user = User.objects.create_user(
        username=user_name,
        email=email,
        password=password,
    )

    profile_id = str(user.pk).zfill(8)

    if is_student == "1":
        Student_Profile.objects.create(
            student_id=profile_id,
            student_name=user_name,
            user=user,
        )
    else:
        Instructor_Profile.objects.create(
            instructor_id=profile_id,
            instructor_name=user_name,
            user=user,
        )
        

    login(request, user)

    return HttpResponse("User created successfully.", status=200)
    
# ---------------------------------------------------------------------------
# HW5  — courses, lectures, QR uploads, dump
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# HW6  — getUploads
# ---------------------------------------------------------------------------



