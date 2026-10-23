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
