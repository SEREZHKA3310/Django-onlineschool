from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    home,
    courses_list,
    course_create,
    course_update,
    course_delete,
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
    path('', home, name='home'),
    path('courses/', courses_list, name='courses_list'),
    path('courses/add/', course_create, name='course_add'),
    path('courses/<int:pk>/edit/', course_update, name='course_edit'),
    path('courses/<int:pk>/delete/', course_delete, name='course_delete'),

    path('api/', include(router.urls)),
]
