"""
models.py — Data model for AttendanceChimp.

AttendanceChimp is an electronic class attendance tool.  Instructors create
courses and lectures; each lecture is assigned a random QR code.  Students
photograph the QR code and upload the image.  The system decodes the QR code,
matches it to a lecture, and records the attendance.

Entities
--------
- CourseProfile   : extends Django User → instructor-specific data
- StudentProfile  : extends Django User → student-specific data
- Course          : a course taught by one instructor
- Enrollment      : junction table linking students to courses
- Lecture         : a single class meeting (has a QR-code identifier)
- QRCodeUpload    : a student's uploaded QR-code photograph
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinLengthValidator

import logging
import string
import random

logger = logging.getLogger(__name__) # set up tracking, auditing, and debugging
                                                               # allows using logger.warning(), logger.error(), 
                                                               # logger.info(), etc. Better than print() for debuggin... 


# ---------------------------------------------------------------------------
# User profiles
# ---------------------------------------------------------------------------

class Instructor_Profile(models.Model):
    '''
    Table linking instructors to there IDs
    '''
    instructor_id = models.CharField(
        max_length=8,
        validators=[MinLengthValidator(8)],
        primary_key=True,
    )
    instructor_name = models.CharField(max_length=20)    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
    )
    
class Student_Profile(models.Model):
    '''
    Table linking students to there IDs
    '''
    student_id = models.CharField(
        max_length=8,
        validators=[MinLengthValidator(8)],
        primary_key=True,
    )
    student_name = models.CharField(max_length=20)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
    )

# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------

class Course(models.Model):
    '''
`   Table for the course, there ID, name and instructor ID (FK from profile),
and the courses' meeting schedule
    '''
    course_id = models.CharField(
        max_length=5,
        validators=[MinLengthValidator(5)],
        primary_key=True,
    )
    course_name = models.CharField(max_length=20)
    course_instructor = models.ForeignKey(Instructor_Profile,
                                          on_delete=models.SET_NULL,
                                          null=True)
    meeting_schedule = models.CharField(max_length=100)
    
                                    
    
# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------


class Enrollment(models.Model):
    '''
    Table showing which student is enrolled in which classes. This is a many
    to many relationship. One row represents one student-class relationship.
    '''
    student_id = models.ForeignKey(Student_Profile,
                                          on_delete=models.CASCADE)
    course_id = models.ForeignKey(Course,
                                          on_delete=models.CASCADE)

    class Meta:
        '''
        Prevents duplicate rows
        '''
        constraints = [
            models.UniqueConstraint(
                fields=["student_id", "course_id"],
                name="unique_student_course",
            )
        ]

# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

class Lecture(models.Model):
    '''
    Table that associates the course, the date, and a primary key for the
    lecture's QR identifier
    '''
    lecture_name = models.CharField(max_length=20)
    lecture_date = models.DateTimeField()
    course_id = models.ForeignKey(Course,
                                          on_delete=models.CASCADE)
    qr_id = models.CharField(
        max_length=8,
        validators=[MinLengthValidator(8)],
        primary_key=True,
    )
    

# ---------------------------------------------------------------------------
# QR Code Upload
# ---------------------------------------------------------------------------

class QRCodeUpload(models.Model):
    '''
    Table which has a row for every student and every lecture they are supposed
    to attend, as well as a boolean saying whether or not they scanned the
    lecture QR code
    '''
    student_id = models.ForeignKey(Student_Profile,
                                    on_delete=models.CASCADE)
    qr_id = models.ForeignKey(Lecture,
                                on_delete=models.CASCADE,
                                null = True,
                                blank = True      
                              )
    attended = models.BooleanField(default=False)
    image = models.FileField(upload_to="qr_uploads/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        '''
        Prevents duplicate attendance registration
        '''
        constraints = [
            models.UniqueConstraint(
                fields=["student_id", "qr_id"],
                name="unique_student_lecture",
            )
        ]



# ---------------------------------------------------------------------------
# Helper / API functions
# ---------------------------------------------------------------------------



