"""Tests for AttendanceChimp's profile, course, and attendance models."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .models import (
    Course,
    Enrollment,
    Instructor_Profile,
    Lecture,
    QRCodeUpload,
    Student_Profile,
)


class AttendanceModelTests(TestCase):
    """Check relationships, unique pairs, validation, and deletion rules."""

    @classmethod
    def setUpTestData(cls):
        cls.instructor = Instructor_Profile.objects.create(
            instructor_id="INST0001", instructor_name="Dr. Chen"
        )
        cls.student = Student_Profile.objects.create(
            student_id="STUD0001", student_name="Maya"
        )
        cls.other_student = Student_Profile.objects.create(
            student_id="STUD0002", student_name="Leo"
        )
        cls.course = Course.objects.create(
            course_id="CS101",
            course_name="Databases",
            course_instructor=cls.instructor,
            meeting_schedule="Mon/Wed 10:30",
        )
        cls.other_course = Course.objects.create(
            course_id="CS102",
            course_name="Programming",
            course_instructor=cls.instructor,
            meeting_schedule="Tue/Thu 11:00",
        )
        cls.lecture = Lecture.objects.create(
            lecture_name="SQL basics",
            lecture_date=timezone.now(),
            course_id=cls.course,
            qr_id="QR000001",
        )
        cls.other_lecture = Lecture.objects.create(
            lecture_name="Python basics",
            lecture_date=timezone.now(),
            course_id=cls.other_course,
            qr_id="QR000002",
        )
        cls.enrollment = Enrollment.objects.create(
            student_id=cls.student, course_id=cls.course
        )
        cls.attendance = QRCodeUpload.objects.create(
            student_id=cls.student, qr_id=cls.lecture
        )

    def test_records_store_their_relationships(self):
        """Stored rows link back to the intended profiles, course, and lecture."""
        course = Course.objects.get(pk="CS101")
        self.assertEqual(course.course_name, "Databases")
        self.assertEqual(course.meeting_schedule, "Mon/Wed 10:30")
        self.assertEqual(course.course_instructor, self.instructor)
        self.assertEqual(self.instructor.instructor_name, "Dr. Chen")
        self.assertEqual(self.student.student_name, "Maya")
        self.assertEqual(self.lecture.course_id, course)
        self.assertEqual(self.enrollment.student_id, self.student)
        self.assertEqual(self.enrollment.course_id, course)
        self.assertEqual(self.attendance.student_id, self.student)
        self.assertEqual(self.attendance.qr_id, self.lecture)

    def test_attendance_defaults_false_and_can_be_saved_true(self):
        """Attendance starts false and an update persists in the database."""
        self.attendance.refresh_from_db()
        self.assertFalse(self.attendance.attended)
        self.attendance.attended = True
        self.attendance.save()
        self.attendance.refresh_from_db()
        self.assertTrue(self.attendance.attended)

    def test_duplicate_enrollment_is_rejected(self):
        """The database rejects a second copy of a student-course pair."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Enrollment.objects.create(
                    student_id=self.student, course_id=self.course
                )
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_duplicate_attendance_is_rejected(self):
        """The database rejects a second copy of a student-lecture pair."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                QRCodeUpload.objects.create(
                    student_id=self.student, qr_id=self.lecture
                )
        self.assertEqual(QRCodeUpload.objects.count(), 1)

    def test_distinct_pairs_are_allowed(self):
        """Pair uniqueness still allows many students and many courses/lectures."""
        Enrollment.objects.create(student_id=self.student, course_id=self.other_course)
        Enrollment.objects.create(student_id=self.other_student, course_id=self.course)
        QRCodeUpload.objects.create(student_id=self.student, qr_id=self.other_lecture)
        QRCodeUpload.objects.create(student_id=self.other_student, qr_id=self.lecture)
        self.assertEqual(Enrollment.objects.count(), 3)
        self.assertEqual(QRCodeUpload.objects.count(), 3)

    def test_deleting_student_removes_only_their_related_rows(self):
        """CASCADE removes this student's rows while preserving other records."""
        other_enrollment = Enrollment.objects.create(
            student_id=self.other_student, course_id=self.course
        )
        other_attendance = QRCodeUpload.objects.create(
            student_id=self.other_student, qr_id=self.lecture
        )
        enrollment_pk = self.enrollment.pk
        attendance_pk = self.attendance.pk
        self.student.delete()
        self.assertFalse(Enrollment.objects.filter(pk=enrollment_pk).exists())
        self.assertFalse(QRCodeUpload.objects.filter(pk=attendance_pk).exists())
        self.assertTrue(Enrollment.objects.filter(pk=other_enrollment.pk).exists())
        self.assertTrue(QRCodeUpload.objects.filter(pk=other_attendance.pk).exists())
        self.assertTrue(Course.objects.filter(pk=self.course.pk).exists())
        self.assertTrue(Lecture.objects.filter(pk=self.lecture.pk).exists())

    def test_deleting_course_cascades_without_deleting_profiles(self):
        """Deleting a course removes its lectures, enrollments, and attendance."""
        enrollment_pk = self.enrollment.pk
        attendance_pk = self.attendance.pk
        lecture_pk = self.lecture.pk
        self.course.delete()
        self.assertFalse(Lecture.objects.filter(pk=lecture_pk).exists())
        self.assertFalse(Enrollment.objects.filter(pk=enrollment_pk).exists())
        self.assertFalse(QRCodeUpload.objects.filter(pk=attendance_pk).exists())
        self.assertTrue(Student_Profile.objects.filter(pk=self.student.pk).exists())
        self.assertTrue(Instructor_Profile.objects.filter(pk=self.instructor.pk).exists())
        self.assertTrue(Course.objects.filter(pk=self.other_course.pk).exists())
        self.assertTrue(Lecture.objects.filter(pk=self.other_lecture.pk).exists())

    def test_deleting_instructor_keeps_courses_and_clears_reference(self):
        """SET_NULL keeps courses when their instructor is deleted."""
        self.instructor.delete()
        self.course.refresh_from_db()
        self.other_course.refresh_from_db()
        self.assertIsNone(self.course.course_instructor)
        self.assertIsNone(self.other_course.course_instructor)
        self.assertTrue(Lecture.objects.filter(pk=self.lecture.pk).exists())

    def test_fixed_length_ids_are_validated(self):
        """full_clean rejects IDs shorter or longer than the declared length."""
        cases = [
            (Instructor_Profile(instructor_name="Test"), "instructor_id", 8),
            (Student_Profile(student_name="Test"), "student_id", 8),
            (Course(course_name="Test", course_instructor=self.instructor,
                    meeting_schedule="Friday"), "course_id", 5),
            (Lecture(lecture_name="Test", lecture_date=timezone.now(),
                     course_id=self.course), "qr_id", 8),
        ]
        for obj, field, length in cases:
            with self.subTest(model=type(obj).__name__, length="valid"):
                setattr(obj, field, "X" * length)
                obj.full_clean()
            for invalid_length in (length - 1, length + 1):
                with self.subTest(model=type(obj).__name__, length=invalid_length):
                    setattr(obj, field, "X" * invalid_length)
                    with self.assertRaises(ValidationError) as error:
                        obj.full_clean()
                    self.assertIn(field, error.exception.message_dict)



import base64
import tempfile
from datetime import datetime, time
from zoneinfo import ZoneInfo
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import resolve, reverse

from . import views
from .models import (
    Course, CourseMeeting, Enrollment, Instructor_Profile,
    Lecture, QRCodeUpload, Student_Profile,
)


class AttendanceHW5Tests(TestCase):
    password = "HW5-test-password-42"
    chicago = ZoneInfo("America/Chicago")
    endpoint_names = (
        "createCourse", "createLecture", "createQRCodeUpload", "dumpUploads",
    )

    @classmethod
    def setUpTestData(cls):
        cls.teacher_user = User.objects.create_user(
            username="test_teacher", password=cls.password,
        )
        cls.teacher = Instructor_Profile.objects.create(
            instructor_id="00000001", instructor_name="Test Teacher",
            user=cls.teacher_user,
        )
        other_user = User.objects.create_user(
            username="other_teacher", password=cls.password,
        )
        cls.other_teacher = Instructor_Profile.objects.create(
            instructor_id="00000002", instructor_name="Other Teacher",
            user=other_user,
        )
        # Names deliberately put the unsubmitted student first alphabetically.
        cls.student_user = User.objects.create_user(
            username="a_missing", password=cls.password,
        )
        cls.student = Student_Profile.objects.create(
            student_id="00000003", student_name="Missing Student",
            user=cls.student_user,
        )
        cls.second_user = User.objects.create_user(
            username="z_uploaded", password=cls.password,
        )
        cls.second_student = Student_Profile.objects.create(
            student_id="00000004", student_name="Uploaded Student",
            user=cls.second_user,
        )
        cls.no_profile_user = User.objects.create_user(
            username="no_profile", password=cls.password,
        )
        cls.course = Course.objects.create(
            course_id="99990", course_name="Existing Course",
            course_instructor=cls.teacher,
        )
        cls.other_course = Course.objects.create(
            course_id="99989", course_name="Other Course",
            course_instructor=cls.other_teacher,
        )
        for student in (cls.student, cls.second_student):
            Enrollment.objects.create(student_id=student, course_id=cls.course)
        cls.lecture = Lecture.objects.create(
            lecture_name="Existing lecture",
            lecture_date=datetime(2026, 11, 10, 9, 30, tzinfo=cls.chicago),
            course_id=cls.course, qr_id="12345678",
        )
        cls.other_lecture = Lecture.objects.create(
            lecture_name="Other lecture",
            lecture_date=datetime(2026, 11, 10, 11, 0, tzinfo=cls.chicago),
            course_id=cls.other_course, qr_id="87654321",
        )
        for student in (cls.student, cls.second_student):
            QRCodeUpload.objects.create(
                student_id=student, qr_id=cls.lecture, image="",
                attended=False, uploaded_at=None,
            )
        # This record must not leak into the selected lecture's report.
        QRCodeUpload.objects.create(
            student_id=cls.student, qr_id=cls.other_lecture,
            image="", attended=False, uploaded_at=None,
        )

    def setUp(self):
        # Uploaded files are written here, never to the project's real media.
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.enterContext(self.settings(MEDIA_ROOT=media.name))

    def login_as(self, user):
        self.client.logout()
        self.assertTrue(self.client.login(
            username=user.username, password=self.password,
        ))

    def course_data(self, **changes):
        data = {
            "course-id": "99991", "course-name": "HW5 Test",
            "start-time": "09:30", "end-time": "10:20",
            "day-mon": "1", "day-wed": "1",
        }
        data.update(changes)
        return data

    def lecture_data(self, **changes):
        data = {
            "choice": self.course.course_name,
            "lecture-name": "Newton's Laws",
            "lecture-date": "2026-11-12T14:35",
        }
        data.update(changes)
        return data

    def image_file(self):
        # A small PNG; QR decoding is intentionally outside this view's scope.
        image = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lE"
            "QVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
        )
        return SimpleUploadedFile("qr.png", image, content_type="image/png")

    def assert_status(self, response, expected):
        self.assertEqual(
            response.status_code, expected,
            response.content.decode(errors="replace")[:1000],
        )

    def test_endpoint_urls_and_view_mappings(self):
        for name in self.endpoint_names:
            with self.subTest(endpoint=name):
                url = reverse(name)
                self.assertEqual(url, f"/app/{name}")
                self.assertEqual(resolve(url).func, getattr(views, name))

    def test_builtin_login_page_and_session(self):
        self.assert_status(self.client.get("/accounts/login/"), 200)
        response = self.client.post("/accounts/login/", {
            "username": self.teacher_user.username, "password": self.password,
        })
        # Django's built-in login redirects after successful authentication.
        self.assert_status(response, 302)
        self.assertEqual(
            self.client.session.get("_auth_user_id"), str(self.teacher_user.pk),
        )

    def test_logged_out_users_receive_401(self):
        for name in self.endpoint_names:
            with self.subTest(endpoint=name):
                method = self.client.get if name == "dumpUploads" else self.client.post
                self.assert_status(method(reverse(name)), 401)

    def test_wrong_roles_receive_401(self):
        self.login_as(self.student_user)
        for name in ("createCourse", "createLecture", "dumpUploads"):
            with self.subTest(endpoint=name):
                method = self.client.get if name == "dumpUploads" else self.client.post
                self.assert_status(method(reverse(name)), 401)
        self.login_as(self.teacher_user)
        self.assert_status(self.client.post(reverse("createQRCodeUpload")), 401)

    def test_user_without_profile_receives_401(self):
        self.login_as(self.no_profile_user)
        for name in self.endpoint_names:
            with self.subTest(endpoint=name):
                method = self.client.get if name == "dumpUploads" else self.client.post
                self.assert_status(method(reverse(name)), 401)

    def test_wrong_http_methods_are_rejected(self):
        self.login_as(self.teacher_user)
        for name in ("createCourse", "createLecture", "createQRCodeUpload"):
            with self.subTest(endpoint=name):
                self.assert_status(self.client.get(reverse(name)), 400)
        self.assert_status(self.client.post(reverse("dumpUploads")), 400)

    def test_create_course_saves_instructor_and_all_meeting_days(self):
        self.login_as(self.teacher_user)
        self.assert_status(self.client.post(
            reverse("createCourse"), self.course_data(),
        ), 200)
        course = Course.objects.get(course_id="99991")
        self.assertEqual(course.course_name, "HW5 Test")
        self.assertEqual(course.course_instructor, self.teacher)
        meetings = CourseMeeting.objects.filter(course=course).order_by("day")
        self.assertEqual(list(meetings.values_list("day", flat=True)), ["mon", "wed"])
        for meeting in meetings:
            self.assertEqual(meeting.start_time, time(9, 30))
            self.assertEqual(meeting.end_time, time(10, 20))

    def test_create_course_rejects_duplicate_id_and_name(self):
        self.login_as(self.teacher_user)
        for changes in (
            {"course-id": self.course.pk},
            {"course-name": self.course.course_name},
        ):
            with self.subTest(changes=changes):
                self.assert_status(self.client.post(
                    reverse("createCourse"), self.course_data(**changes),
                ), 400)
        self.assertEqual(Course.objects.count(), 2)
        self.assertEqual(CourseMeeting.objects.count(), 0)

    def test_create_course_rejects_invalid_inputs_without_writes(self):
        self.login_as(self.teacher_user)
        invalid = [
            {"course-id": "1234"}, {"course-id": "123456"},
            {"course-name": ""}, {"course-name": "   "},
            {"course-name": "x" * 21}, {"start-time": "invalid"},
            {"end-time": ""}, {"end-time": "09:00"},
            {"end-time": "09:30"},
        ]
        for changes in invalid:
            with self.subTest(changes=changes):
                self.assert_status(self.client.post(
                    reverse("createCourse"), self.course_data(**changes),
                ), 400)
        data = self.course_data()
        del data["day-mon"]
        del data["day-wed"]
        self.assert_status(self.client.post(reverse("createCourse"), data), 400)
        self.assertEqual(Course.objects.count(), 2)
        self.assertEqual(CourseMeeting.objects.count(), 0)

    def test_create_lecture_saves_inputs_and_initial_attendance_rows(self):
        self.login_as(self.teacher_user)
        self.assert_status(self.client.post(
            reverse("createLecture"), self.lecture_data(),
        ), 200)
        lecture = Lecture.objects.get(
            course_id=self.course, lecture_name="Newton's Laws",
        )
        self.assertRegex(lecture.qr_id, r"^[0-9]{8}$")
        self.assertNotEqual(lecture.qr_id, self.lecture.qr_id)
        self.assertEqual(
            lecture.lecture_date.astimezone(self.chicago),
            datetime(2026, 11, 12, 14, 35, tzinfo=self.chicago),
        )
        rows = QRCodeUpload.objects.filter(qr_id=lecture)
        self.assertEqual(rows.count(), 2)
        self.assertEqual(
            {row.student_id for row in rows},
            {self.student, self.second_student},
        )
        for row in rows:
            self.assertFalse(row.attended)
            self.assertFalse(row.image)
            self.assertIsNone(row.uploaded_at)

    def test_create_lecture_rejects_invalid_inputs_without_writes(self):
        self.login_as(self.teacher_user)
        for changes in (
            {"choice": ""}, {"choice": "Missing course"},
            {"lecture-name": ""}, {"lecture-name": "   "},
            {"lecture-name": "x" * 21}, {"lecture-date": ""},
            {"lecture-date": "2026-02-30T10:00"},
        ):
            with self.subTest(changes=changes):
                self.assert_status(self.client.post(
                    reverse("createLecture"), self.lecture_data(**changes),
                ), 400)
        self.assertEqual(Lecture.objects.count(), 2)
        self.assertEqual(QRCodeUpload.objects.count(), 3)

    def test_create_lecture_rejects_another_instructors_course(self):
        self.login_as(self.teacher_user)
        self.assert_status(self.client.post(
            reverse("createLecture"),
            self.lecture_data(**{"choice": self.other_course.course_name}),
        ), 403)
        self.assertEqual(Lecture.objects.count(), 2)

    def test_duplicate_lecture_names_are_rejected_only_within_same_course(self):
        self.login_as(self.teacher_user)
        self.assert_status(self.client.post(
            reverse("createLecture"),
            self.lecture_data(**{"lecture-name": self.lecture.lecture_name}),
        ), 400)
        own_second_course = Course.objects.create(
            course_id="99988", course_name="Second Own Course",
            course_instructor=self.teacher,
        )
        self.assert_status(self.client.post(
            reverse("createLecture"), self.lecture_data(**{
                "choice": own_second_course.course_name,
                "lecture-name": self.lecture.lecture_name,
            }),
        ), 200)

    def test_upload_updates_existing_row_and_saves_file_and_time(self):
        self.login_as(self.student_user)
        row = QRCodeUpload.objects.get(student_id=self.student, qr_id=self.lecture)
        original_pk = row.pk
        original_count = QRCodeUpload.objects.count()
        self.assert_status(self.client.post(reverse("createQRCodeUpload"), {
            "qr-id": self.lecture.qr_id, "imageUpload": self.image_file(),
        }), 200)
        row.refresh_from_db()
        self.assertEqual(row.pk, original_pk)
        self.assertEqual(QRCodeUpload.objects.count(), original_count)
        self.assertTrue(row.attended)
        self.assertIsNotNone(row.uploaded_at)
        self.assertTrue(row.image.storage.exists(row.image.name))
        other_row = QRCodeUpload.objects.get(
            student_id=self.second_student, qr_id=self.lecture,
        )
        self.assertFalse(other_row.attended)
        self.assertIsNone(other_row.uploaded_at)

    def test_upload_requires_file_lecture_and_existing_student_record(self):
        self.login_as(self.second_user)
        for data in (
            {"qr-id": self.lecture.qr_id},
            {"imageUpload": self.image_file()},
            {"qr-id": "00000000", "imageUpload": self.image_file()},
            # A different student's row exists, but this student's does not.
            {"qr-id": self.other_lecture.qr_id, "imageUpload": self.image_file()},
        ):
            with self.subTest(fields=list(data)):
                self.assert_status(self.client.post(
                    reverse("createQRCodeUpload"), data,
                ), 400)
        self.assertEqual(QRCodeUpload.objects.count(), 3)
        self.assertFalse(QRCodeUpload.objects.filter(attended=True).exists())

    def test_dump_uploads_returns_submitted_first_with_exact_keys(self):
        timestamp = datetime(2026, 11, 10, 9, 25, tzinfo=self.chicago)
        QRCodeUpload.objects.filter(
            student_id=self.second_student, qr_id=self.lecture,
        ).update(attended=True, uploaded_at=timestamp)
        self.login_as(self.teacher_user)
        response = self.client.get(reverse("dumpUploads"), {
            "qr-id": self.lecture.qr_id,
        })
        self.assert_status(response, 200)
        self.assertEqual(response.json(), [
            {"username": "z_uploaded", "upload_time": "2026-11-10 09:25:00"},
            {"username": "a_missing", "upload_time": None},
        ])

    def test_dump_uploads_rejects_missing_unknown_or_other_instructors_lecture(self):
        self.login_as(self.teacher_user)
        for data, status in (
            ({}, 400),
            ({"qr-id": "00000000"}, 400),
            ({"qr-id": self.other_lecture.qr_id}, 403),
        ):
            with self.subTest(data=data):
                self.assert_status(self.client.get(reverse("dumpUploads"), data), status)

    def test_complete_lecture_upload_and_report_workflow(self):
        self.login_as(self.teacher_user)
        self.assert_status(self.client.post(
            reverse("createLecture"), self.lecture_data(),
        ), 200)
        lecture = Lecture.objects.get(
            course_id=self.course, lecture_name="Newton's Laws",
        )
        self.login_as(self.second_user)
        self.assert_status(self.client.post(reverse("createQRCodeUpload"), {
            "qr-id": lecture.qr_id, "imageUpload": self.image_file(),
        }), 200)
        self.login_as(self.teacher_user)
        response = self.client.get(reverse("dumpUploads"), {"qr-id": lecture.qr_id})
        self.assert_status(response, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["username"], self.second_user.username)
        self.assertIsNotNone(data[0]["upload_time"])
        self.assertEqual(data[1], {
            "username": self.student_user.username, "upload_time": None,
        })





