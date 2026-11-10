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

from .models import *

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


@csrf_exempt
def createCourse(request):
    """Create a course with the instructor's chosen weekly schedule."""
    if request.method != "POST":
        return HttpResponseBadRequest("Only POST requests are allowed.")

    if not request.user.is_authenticated:
        return HttpResponse("Instructor login required.", status=401)

    try:
        instructor = Instructor_Profile.objects.get(user=request.user)
    except Instructor_Profile.DoesNotExist:
        return HttpResponse("Instructor login required.", status=401)

    course_name = request.POST.get("course-name", "").strip()
    course_id = request.POST.get("course-id", "").strip()
    start_time = request.POST.get("start-time", "")
    end_time = request.POST.get("end-time", "")

    # Read the selected weekday checkboxes.
    days = [
        day
        for day in ["mon", "tue", "wed", "thu", "fri"]
        if f"day-{day}" in request.POST
    ]

    if not course_name or len(course_name) > 20:
        return HttpResponseBadRequest(
            "Course name must be between 1 and 20 characters."
        )

    if Course.objects.filter(course_name=course_name).exists():
        return HttpResponseBadRequest(
            "This course name is already taken."
        )

    if course_id:
        if len(course_id) > 20:
            return HttpResponseBadRequest(
                "Course ID must be 20 characters or fewer."
            )

        if Course.objects.filter(course_id=course_id).exists():
            return HttpResponseBadRequest(
                "This course ID is already taken."
            )
    else:
        # Preserve support for HW5 requests that omit the course ID.
        while True:
            course_id = str(random.randint(0, 99999)).zfill(5)
            if not Course.objects.filter(course_id=course_id).exists():
                break

    if not days:
        return HttpResponseBadRequest("Select at least one day.")

    # Convert the form's HH:MM strings into time objects.
    try:
        start = datetime.strptime(start_time, "%H:%M").time()
        end = datetime.strptime(end_time, "%H:%M").time()
    except ValueError:
        return HttpResponseBadRequest(
            "Provide valid start and end times."
        )

    if end <= start:
        return HttpResponseBadRequest(
            "End time must be after start time."
        )

    course = Course.objects.create(
        course_id=course_id,
        course_name=course_name,
        course_instructor=instructor,
        mon="mon" in days,
        tue="tue" in days,
        wed="wed" in days,
        thu="thu" in days,
        fri="fri" in days,
        start_time=start,
        end_time=end,
    )

    return HttpResponse(
        f"Course created. ID: {course.course_id}",
        status=200,
    )


import random

@csrf_exempt
def createLecture(request):
    '''
    Creates a lecture for a course owned by the logged-in instructor.
    Lecture names must be unique within that course.
    Generates a random eight-digit QR identifier.
    '''
    if request.method != "POST":
        return HttpResponseBadRequest("Only POST requests are allowed.")

    if not request.user.is_authenticated:
        return HttpResponse("Instructor login required.", status=401)

    try:
        instructor = Instructor_Profile.objects.get(user=request.user)
    except Instructor_Profile.DoesNotExist:
        return HttpResponse("Instructor login required.", status=401)

    course_name = request.POST.get("choice", "").strip()
    lecture_name = request.POST.get("lecture-name", "").strip()
    lecture_date_text = request.POST.get("lecture-date", "")

    if lecture_date_text:
        try:
            lecture_date = datetime.strptime(
                lecture_date_text, "%Y-%m-%dT%H:%M"
            ).replace(tzinfo=CDT)
        except ValueError:
            return HttpResponseBadRequest(
                "Provide a valid lecture date and time."
            )
        
    else:
        lecture_date = datetime.now(CDT)

    if not course_name:
        return HttpResponseBadRequest("Select a course.")


    if len(lecture_name) > 20:
        return HttpResponseBadRequest(
            "Lecture name must be 20 characters or fewer."
        )    

    try:
        course = Course.objects.get(course_name=course_name)
    except Course.DoesNotExist:
        return HttpResponseBadRequest("Course does not exist.")
    except Course.MultipleObjectsReturned:
        return HttpResponseBadRequest(
            "Course name is ambiguous. Please resolve duplicate course names."
        )

    if course.course_instructor != instructor:
        return HttpResponseForbidden(
            "You can only create lectures for your own courses."
        )

    if not lecture_name:
        number = Lecture.objects.filter(course_id=course).count() + 1
        lecture_name = f"Lecture {number}"

        while Lecture.objects.filter(
            course_id=course,
            lecture_name=lecture_name,
        ).exists():
            number += 1
            lecture_name = f"Lecture {number}"

    if Lecture.objects.filter(
        course_id=course,
        lecture_name=lecture_name,
    ).exists():
        return HttpResponseBadRequest(
            "A lecture with this name already exists in this course."
        )

    while True:
        qr_id = str(random.randint(0, 99999999)).zfill(8)
        if not Lecture.objects.filter(qr_id=qr_id).exists():
            break

    lecture = Lecture.objects.create(
        lecture_name=lecture_name,
        lecture_date=lecture_date,
        course_id=course,
        qr_id=qr_id,
    )

    # When we make a lecture, add a row to QR Uploads for every student and set
    # attended to False
    enrollments = Enrollment.objects.filter(course_id=course)

    for enrollment in enrollments:
        QRCodeUpload.objects.create(
            student_id=enrollment.student_id,
            qr_id=lecture,
            attended=False,
            image="",
        )

    return HttpResponse(
        f"Lecture created. QR ID: {lecture.qr_id}",
        status=200,
    )

    
@csrf_exempt
def createQRCodeUpload(request):
    '''
    When a student scans the qr code, look for the right student-id, qr row that should already
    be in QR Code upload, and change attended from false to true.
    '''
    if request.method != "POST":
        return HttpResponseBadRequest("Only POST requests are allowed.")

    if not request.user.is_authenticated:
        return HttpResponse("Student login required.", status=401)

    try:
        student = Student_Profile.objects.get(user=request.user)
    except Student_Profile.DoesNotExist:
        return HttpResponse("Student login required.", status=401)

    image = request.FILES.get("imageUpload")
    qr_id = request.POST.get("qr-id", "").strip()

    if not image:
        return HttpResponseBadRequest("Upload an image.")

    if qr_id:
        try:
            upload = QRCodeUpload.objects.get(
                student_id=student,
                qr_id=qr_id,
            )
        except QRCodeUpload.DoesNotExist:
            return HttpResponseBadRequest(
                "No attendance record exists for this student and lecture."
            )
    else:
        upload = QRCodeUpload(
            student_id=student,
            qr_id=None,
        )


    upload.image = image
    upload.attended = True
    upload.uploaded_at = datetime.now(CDT)
    upload.save()

    return HttpResponse("QR code uploaded.", status=200)


def dumpUploads(request):
    '''
    Lets the instructor get the data on all student qr code uploads. Returns rows where the
    student uploaded the qr code on top and where the didn't on bottom.
    '''
    if request.method != "GET":
        return HttpResponseBadRequest("Only GET requests are allowed.")

    if not request.user.is_authenticated:
        return HttpResponse("Instructor login required.", status=401)

    try:
        instructor = Instructor_Profile.objects.get(user=request.user)
    except Instructor_Profile.DoesNotExist:
        return HttpResponse("Instructor login required.", status=401)

    qr_id = request.GET.get("qr-id", "").strip()

    records = (
        QRCodeUpload.objects
        .select_related("student_id__user")
        .order_by("-attended", "student_id__user__username")
    )

    if qr_id:
        try:
            lecture = Lecture.objects.get(qr_id=qr_id)
        except Lecture.DoesNotExist:
            return HttpResponseBadRequest("Lecture does not exist.")

        if lecture.course_id.course_instructor != instructor:
            return HttpResponseForbidden(
                "You can only view uploads for your own courses."
            )

        records = records.filter(qr_id=lecture)
    else:
        records = records.filter(
            attended=True,
            uploaded_at__isnull=False,
        )

    data = []

    for record in records:
        upload_time = None

        if record.attended and record.uploaded_at:
            upload_time = record.uploaded_at.astimezone(CDT).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        data.append({
            "username": record.student_id.user.username,
            "upload_time": upload_time,
        })

    return JsonResponse(data, safe=False)




def new_course(request):
    '''
    Checks if the user is an instructor and displays the course form.
    '''
    if request.method != "GET":
        return HttpResponseBadRequest("Only GET requests are allowed.")

    if (
        not request.user.is_authenticated
        or not Instructor_Profile.objects.filter(user=request.user).exists()
    ):
        return HttpResponse("Instructor login required.", status=401)

    return render(request, "app/new_course.html")



def new_lecture(request):
    '''
    Checks if the user is an instructor and displays the lecture form
    '''
    if request.method != "GET":
        return HttpResponseBadRequest("Only GET requests are allowed.")

    if (
        not request.user.is_authenticated
        or not Instructor_Profile.objects.filter(user=request.user).exists()
    ):
        return HttpResponse("Instructor login required.", status=401)

    courses = Course.objects.filter(
        course_instructor__user=request.user
    )

    return render(request, "app/new_lecture.html", {"courses": courses})


def new_qr_upload(request):
    '''
    Checks that the user is a student, and supplies the associated lectures to the upload
    form’s dropdown.
    '''
    if request.method != "GET":
        return HttpResponseBadRequest("Only GET requests are allowed.")

    if (
        not request.user.is_authenticated
        or not Student_Profile.objects.filter(user=request.user).exists()
    ):
        return HttpResponse("Student login required.", status=401)

    records = QRCodeUpload.objects.filter(
        student_id__user=request.user,
        qr_id__isnull=False,
    ).select_related("qr_id")

    return render(request, "app/new_qr_upload.html", {"records": records})


# ---------------------------------------------------------------------------
# HW6  — getUploads
# ---------------------------------------------------------------------------

from django.http import JsonResponse


def getUploads(request):
    '''
    Takes a get request and displays the valid qr uploads for a given course
    '''
    if request.method != "GET":
        return HttpResponseBadRequest("Only GET requests are allowed.")

    if (
        not request.user.is_authenticated
        or not Instructor_Profile.objects.filter(user=request.user).exists()
    ):
        return HttpResponse("Instructor login required.", status=401)

    course = request.GET.get("course", "").strip()

    if not course:
        return JsonResponse(
            {"error": "Missing course parameter"},
            status=400,
        )

    uploads = getUploadsForCourse(course)

    data = []

    for upload in uploads:
        data.append({
            "username": upload.student_id.user.username,
            "upload_time": upload.uploaded_at.astimezone(CDT).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        })

    return JsonResponse(data, safe=False)    
    

    

    

