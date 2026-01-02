from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CourseViewSet,
    LessonViewSet,
    AssignmentViewSet,
    SubmissionViewSet,
    EnrollmentViewSet,
    ProgressViewSet
)

router = DefaultRouter()
router.register("courses", CourseViewSet, basename="courses")
router.register("lessons", LessonViewSet, basename="lessons")
router.register("assignments", AssignmentViewSet, basename="assignments")
router.register("submissions", SubmissionViewSet, basename="submissions")
router.register("enrollments", EnrollmentViewSet, basename="enrollments")
router.register("progress", ProgressViewSet, basename="progress")

urlpatterns = [
    path("api/", include(router.urls)),
]
