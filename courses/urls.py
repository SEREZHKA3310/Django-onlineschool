"""Маршруты веб-интерфейса и REST API приложения courses."""

from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import views_web
from .views import (
    AssignmentViewSet,
    CourseViewSet,
    EnrollmentViewSet,
    LessonViewSet,
    ProgressViewSet,
    SubmissionViewSet,
)

def trigger_error(request):
    division_by_zero = 1 / 0
    return HttpResponse("Сюда код не дойдет")

router = DefaultRouter()
router.register("courses", CourseViewSet, basename="courses")
router.register("lessons", LessonViewSet, basename="lessons")
router.register("assignments", AssignmentViewSet, basename="assignments")
router.register("submissions", SubmissionViewSet, basename="submissions")
router.register("enrollments", EnrollmentViewSet, basename="enrollments")
router.register("progress", ProgressViewSet, basename="progress")

urlpatterns = [
    path("", views_web.home, name="home"),
    path("login/", views_web.login_view, name="login"),
    path("register/", views_web.register_view, name="register"),
    path("logout/", views_web.logout_view, name="logout"),
    path("courses/", views_web.courses_list, name="courses_list"),
    path("courses/add/", views_web.course_create, name="course_add"),
    path("courses/<int:pk>/", views_web.course_detail, name="course_detail"),
    path("courses/<int:pk>/edit/", views_web.course_update, name="course_edit"),
    path("courses/<int:pk>/delete/", views_web.course_delete, name="course_delete"),
    path("courses/<int:pk>/enroll/", views_web.course_enroll, name="course_enroll"),
    path("courses/<int:course_pk>/lessons/add/", views_web.lesson_create, name="lesson_add"),
    path("lessons/<int:pk>/edit/", views_web.lesson_update, name="lesson_edit"),
    path("lessons/<int:pk>/delete/", views_web.lesson_delete, name="lesson_delete"),
    path("lessons/<int:pk>/complete/", views_web.lesson_complete, name="lesson_complete"),
    path("lessons/<int:lesson_pk>/assignments/add/", views_web.assignment_create, name="assignment_add"),
    path("assignments/<int:pk>/edit/", views_web.assignment_update, name="assignment_edit"),
    path("assignments/<int:pk>/delete/", views_web.assignment_delete, name="assignment_delete"),
    path("assignments/<int:pk>/submit/", views_web.submit_assignment, name="submit_assignment"),
    path("my/courses/", views_web.my_courses, name="my_courses"),
    path("my/submissions/", views_web.my_submissions, name="my_submissions"),
    path("reviews/", views_web.submissions_list, name="submissions_list"),
    path("reviews/<int:pk>/", views_web.submission_grade, name="submission_grade"),
    path("analytics/", views_web.analytics, name="analytics"),
    path("api/auth/login/", obtain_auth_token, name="api_login"),
    path("api/", include(router.urls)),

    path('sentry-debug/', trigger_error)
]
