'''
Claude Prompt: I need some help on an assignment. First I need you to help
design a schema for this task. I am designing an app that is going to track
attendance for classes. This app needs to track attendance data by having
students scan QR codes. It needs to have these tables: InstructorProfile /
StudentProfile tables (instead of one Users table – think why. . .),
Course table with at least name, instructor, meeting schedule,
Enrollment table: links students to courses (many-to-many),
Lecture table: linked to a course, has a date and a QR identifier,
QRCodeUpload table: linked to a student and (optionally) a lecture 
'''

'''
Follow up Prompt: I want you to implement this schema using Django. Write the
code for models.py only.
'''




"""
Attendance tracking models: students scan a per-lecture QR code.

Requires Django 5.1+ (CheckConstraint uses `condition=`; on older versions
change it to `check=`).
"""
import secrets

from django.conf import settings
from django.db import models
from django.db.models import F, Q


def generate_qr_identifier():
    """Unguessable token that gets encoded into a lecture's QR code."""
    return secrets.token_urlsafe(32)  # 43 characters


class InstructorProfile(models.Model):
    """Instructor-only data. Login/credentials live on Django's User model."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="instructor_profile",
    )
    department = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.get_username()


class StudentProfile(models.Model):
    """Student-only data. Login/credentials live on Django's User model."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    student_number = models.CharField(max_length=50, unique=True)  # campus ID
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        name = self.user.get_full_name() or self.user.get_username()
        return f"{name} ({self.student_number})"


class Course(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30, blank=True)  # e.g. "CMSC 12300"
    term = models.CharField(max_length=30, blank=True)  # e.g. "Autumn 2026"
    instructor = models.ForeignKey(
        InstructorProfile,
        on_delete=models.PROTECT,  # can't delete an instructor who still has courses
        related_name="courses",
    )

    # Meeting schedule
    meeting_days = models.CharField(
        max_length=20,
        help_text='Days the course meets, e.g. "MWF" or "Tue,Thu".',
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=100, blank=True)

    # Many-to-many to students, resolved through Enrollment
    students = models.ManyToManyField(
        StudentProfile,
        through="Enrollment",
        related_name="courses",
    )

    class Meta:
        ordering = ["term", "code", "name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")),
                name="course_end_after_start",
            ),
        ]

    def __str__(self):
        return f"{self.code} {self.name}".strip()


class Enrollment(models.Model):
    """Join table: which students are in which courses."""

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="enrollments"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="enrollments"
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "course"], name="unique_enrollment"
            ),
        ]

    def __str__(self):
        return f"{self.student} in {self.course}"


class Lecture(models.Model):
    """One class session. Its qr_identifier is what the displayed QR encodes."""

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="lectures"
    )
    lecture_date = models.DateField()
    qr_identifier = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        default=generate_qr_identifier,
    )
    qr_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional: scans after this time are not counted.",
    )

    class Meta:
        ordering = ["-lecture_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "lecture_date"], name="unique_lecture_per_day"
            ),
        ]

    def __str__(self):
        return f"{self.course} on {self.lecture_date}"


class QRCodeUpload(models.Model):
    """
    Log of every scan a student submits.

    `lecture` is nullable on purpose: if the scanned value doesn't match any
    lecture (bad/mistyped/old code) we still keep the attempt, with the raw
    string in `scanned_value`.
    """

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="qr_uploads"
    )
    lecture = models.ForeignKey(
        Lecture,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploads",
    )
    scanned_value = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.student} scanned at {self.uploaded_at:%Y-%m-%d %H:%M}"

    @property
    def counts_as_attendance(self):
        """
        Attendance is derived, not stored: the scan must match a lecture,
        arrive before the QR expires (if an expiry is set), and come from a
        student enrolled in that lecture's course.
        """
        if self.lecture_id is None:
            return False
        expires = self.lecture.qr_expires_at
        if expires is not None and self.uploaded_at > expires:
            return False
        return Enrollment.objects.filter(
            student_id=self.student_id, course_id=self.lecture.course_id
        ).exists()
