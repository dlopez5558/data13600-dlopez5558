"""HW6 helper/API tests for AttendanceChimp's current model field names.

Save as app/test_hw6.py, then run from the directory containing manage.py:
    python manage.py test app.test_hw6 --verbosity 2

Django creates a separate test database. FileField values below are just
paths: these tests do not create image files or require a running server.
"""

from datetime import datetime, time, timedelta, timezone

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from .models import (
    Course,
    Instructor_Profile,
    Lecture,
    QRCodeUpload,
    Student_Profile,
    getUploadsForCourse,
)


@override_settings(USE_TZ=True, TIME_ZONE="UTC")
class HW6Tests(TestCase):
    """Check the required behavior even when the project timezone is UTC."""

    endpoint = "/app/getUploads"
    weekdays = ("mon", "tue", "wed", "thu", "fri")

    @classmethod
    def setUpTestData(cls):
        cls.instructor_user = User.objects.create_user(username="hw6_instructor")
        cls.instructor = Instructor_Profile.objects.create(
            instructor_id="90000001",
            instructor_name="HW6 instructor",
            user=cls.instructor_user,
        )
        cls.student_user = User.objects.create_user(username="hw6_student")
        cls.student = Student_Profile.objects.create(
            student_id="90000002",
            student_name="HW6 student",
            user=cls.student_user,
        )
        cls.no_profile_user = User.objects.create_user(username="hw6_no_profile")
        cls.course = Course.objects.create(
            course_id="DATA13600",
            course_name="Data Engineering",
            course_instructor=cls.instructor,
            mon=True,
            tue=False,
            wed=True,
            thu=False,
            fri=True,
            start_time=time(10, 0),
            end_time=time(11, 20),
        )
        cls.other_course = Course.objects.create(
            course_id="PHYS24300",
            course_name="Physics",
            course_instructor=cls.instructor,
            mon=True,
            start_time=time(10, 0),
            end_time=time(11, 20),
        )

    def setUp(self):
        self.lecture_number = 80000000

    @staticmethod
    def utc(year=2024, month=11, day=4, hour=16, minute=30, second=0):
        """November 4, 2024, 16:30 UTC is Monday, 10:30 in Chicago."""
        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)

    def make_upload(self, timestamp, course=None, linked=True):
        """Use a distinct lecture so the student/lecture constraint is respected."""
        lecture = None
        if linked:
            self.lecture_number += 1
            lecture = Lecture.objects.create(
                lecture_name=f"Lecture {self.lecture_number}",
                lecture_date=timestamp if timestamp is not None else self.utc(),
                course_id=course if course is not None else self.course,
                qr_id=str(self.lecture_number),
            )
        return QRCodeUpload.objects.create(
            student_id=self.student,
            qr_id=lecture,
            attended=timestamp is not None,
            image="qr_uploads/hw6-test.png" if timestamp is not None else "",
            uploaded_at=timestamp,
        )

    def assert_uploads(self, result, expected):
        self.assertIsInstance(result, list)
        for upload in result:
            self.assertIsInstance(upload, QRCodeUpload)
        self.assertCountEqual(
            [upload.pk for upload in result],
            [upload.pk for upload in expected],
        )

    def test_helper_returns_upload_objects_from_multiple_lectures(self):
        first = self.make_upload(self.utc())
        second = self.make_upload(self.utc(minute=40))
        self.assert_uploads(getUploadsForCourse("DATA13600"), [first, second])

    def test_helper_unknown_course_returns_empty_list(self):
        self.make_upload(self.utc())
        self.assertEqual(getUploadsForCourse("MISSING999"), [])

    def test_helper_existing_course_without_uploads_returns_empty_list(self):
        self.assertEqual(getUploadsForCourse("DATA13600"), [])

    def test_helper_excludes_other_courses_and_unlinked_uploads(self):
        valid = self.make_upload(self.utc())
        self.make_upload(self.utc(), course=self.other_course)
        self.make_upload(self.utc(), linked=False)
        self.assert_uploads(getUploadsForCourse("DATA13600"), [valid])

    def test_helper_checks_each_weekday_flag_and_excludes_weekends(self):
        # Create one upload at 10:30 Chicago time on every day of one week.
        uploads = [
            self.make_upload(self.utc() + timedelta(days=offset))
            for offset in range(7)
        ]
        for index, selected_day in enumerate(self.weekdays):
            with self.subTest(meeting_day=selected_day):
                for day in self.weekdays:
                    setattr(self.course, day, day == selected_day)
                self.course.save(update_fields=list(self.weekdays))
                self.assert_uploads(
                    getUploadsForCourse("DATA13600"), [uploads[index]]
                )

    def test_helper_checks_time_window_and_inclusive_boundaries(self):
        expected = []
        # UTC times below correspond to Chicago 09:59:59 through 11:20:01.
        cases = [(15, 59, 59, False), (16, 0, 0, True),
                 (16, 30, 0, True), (17, 20, 0, True), (17, 20, 1, False)]
        for hour, minute, second, keep in cases:
            upload = self.make_upload(
                self.utc(hour=hour, minute=minute, second=second)
            )
            if keep:
                expected.append(upload)
        self.assert_uploads(getUploadsForCourse("DATA13600"), expected)

    def test_helper_uses_chicago_time_in_winter(self):
        valid = self.make_upload(self.utc(hour=16, minute=30))
        self.make_upload(self.utc(hour=10, minute=30))  # Chicago 04:30.
        self.assert_uploads(getUploadsForCourse("DATA13600"), [valid])

    def test_helper_uses_chicago_time_in_summer(self):
        # July 1, 2024, is Monday; daylight saving makes Chicago UTC-5.
        valid = self.make_upload(self.utc(month=7, day=1, hour=15))
        self.make_upload(self.utc(month=7, day=1, hour=10))  # Chicago 05:30.
        self.assert_uploads(getUploadsForCourse("DATA13600"), [valid])

    def test_helper_uses_chicago_weekday_when_utc_date_differs(self):
        self.course.start_time = time(18, 0)
        self.course.end_time = time(19, 0)
        self.course.save(update_fields=["start_time", "end_time"])
        # Tuesday UTC, but Monday 18:30 Chicago: valid.
        valid = self.make_upload(self.utc(day=5, hour=0, minute=30))
        # Monday UTC, but Sunday 18:30 Chicago: invalid.
        self.make_upload(self.utc(day=4, hour=0, minute=30))
        self.assert_uploads(getUploadsForCourse("DATA13600"), [valid])

    def test_helper_ignores_missing_upload_timestamps(self):
        valid = self.make_upload(self.utc())
        self.make_upload(None)
        self.assert_uploads(getUploadsForCourse("DATA13600"), [valid])

    def test_helper_handles_temporarily_nullable_course_times(self):
        nullable_fields = [
            name for name in ("start_time", "end_time")
            if Course._meta.get_field(name).null
        ]
        if not nullable_fields:
            self.skipTest("Course times are already required by the schema.")
        self.make_upload(self.utc())
        for field in nullable_fields:
            with self.subTest(missing_field=field):
                original = getattr(self.course, field)
                setattr(self.course, field, None)
                self.course.save(update_fields=[field])
                self.assertEqual(getUploadsForCourse("DATA13600"), [])
                setattr(self.course, field, original)
                self.course.save(update_fields=[field])

    def test_endpoint_returns_exactly_valid_uploads_and_required_json(self):
        self.make_upload(self.utc())                       # Valid Monday.
        self.make_upload(self.utc(day=6, minute=40))       # Valid Wednesday.
        self.make_upload(self.utc(hour=15, minute=0))      # Before class.
        self.make_upload(self.utc(day=5))                 # Tuesday.
        self.make_upload(self.utc(), course=self.other_course)
        self.make_upload(self.utc(), linked=False)
        self.make_upload(None)
        self.client.force_login(self.instructor_user)
        response = self.client.get(self.endpoint, {"course": "DATA13600"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.headers["Content-Type"], "application/json")
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertCountEqual(data, [
            {"username": "hw6_student", "upload_time": "2024-11-04 10:30:00"},
            {"username": "hw6_student", "upload_time": "2024-11-06 10:40:00"},
        ])
        for entry in data:
            self.assertEqual(set(entry), {"username", "upload_time"})
            self.assertIsInstance(entry["upload_time"], str)

    def test_endpoint_unknown_course_returns_200_and_empty_list(self):
        self.client.force_login(self.instructor_user)
        response = self.client.get(self.endpoint, {"course": "MISSING999"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), [])

    def test_endpoint_existing_course_without_uploads_returns_empty_list(self):
        self.client.force_login(self.instructor_user)
        response = self.client.get(self.endpoint, {"course": "DATA13600"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), [])

    def test_endpoint_missing_course_returns_exact_400_error(self):
        self.client.force_login(self.instructor_user)
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json(), {"error": "Missing course parameter"})

    def test_endpoint_unauthorized_users_receive_401(self):
        for role, user in (("logged out", None), ("student", self.student_user),
                           ("no profile", self.no_profile_user)):
            self.client.logout()
            if user is not None:
                self.client.force_login(user)
            for params in ({"course": "DATA13600"}, {}):
                with self.subTest(role=role, parameters=params):
                    response = self.client.get(self.endpoint, params)
                    self.assertEqual(response.status_code, 401, response.content)

    def test_endpoint_rejects_post_requests(self):
        self.client.force_login(self.instructor_user)
        response = self.client.post(self.endpoint, {"course": "DATA13600"})
        self.assertIn(response.status_code, (400, 405), response.content)
