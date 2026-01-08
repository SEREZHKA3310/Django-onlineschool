from datetime import timedelta

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from django.db.models import Q, Count

from .models import (
    Course, Lesson, Assignment, Submission, Enrollment, Progress
)
from .serializers import (
    CourseSerializer, LessonSerializer, AssignmentSerializer,
    SubmissionSerializer, EnrollmentSerializer, ProgressSerializer
)


class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer

    filter_backends = [
        DjangoFilterBackend,
        OrderingFilter,
        SearchFilter,
    ]

    filterset_fields = {
        "level": ["exact"],
        "category": ["exact"],
        "teacher": ["exact"],
        "published": ["exact"],
        "price": ["gte", "lte", "exact"],
    }

    search_fields = [
        "name",
        "description",
    ]

    ordering_fields = ["price", "created_at"]
    ordering = ["-created_at"]

    # POST /api/courses/
    def perform_create(self, serializer):
        if not self.request.user.is_teacher:
            raise PermissionDenied("Только преподаватель может создавать курсы")
        serializer.save(teacher=self.request.user)

    # PUT /api/courses/{id}/
    def update(self, request, pk=None):
        course = self.get_object()

        if course.teacher != request.user:
            return Response(
                {"detail": "Только преподаватель может обновить курс."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(course, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    # PATCH /api/courses/{id}/
    def partial_update(self, request, pk=None):
        course = self.get_object()

        if course.teacher != request.user:
            return Response(
                {"detail": "Только преподаватель может обновить курс."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(course, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    # DELETE /api/courses/{id}/
    def destroy(self, request, pk=None):
        course = self.get_object()

        if course.teacher != request.user:
            return Response(
                {"detail": "Только преподаватель может удалить курс."},
                status=status.HTTP_403_FORBIDDEN
            )

        course.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # POST /api/courses/{id}/enroll/
    @action(methods=["POST"], detail=True)
    def enroll(self, request, pk=None):
        course = self.get_object()
        student = request.user

        if Enrollment.objects.filter(student=student, course=course).exists():
            return Response(
                {"detail": "Вы уже записаны на этот курс."},
                status=status.HTTP_400_BAD_REQUEST
            )

        Enrollment.objects.create(student=student, course=course)
        return Response({"detail": "Вы успешно записались на курс."})

    # GET /api/courses/my/
    @action(methods=["GET"], detail=False)
    def my(self, request):
        user = request.user
        courses = (
            Course.objects.filter(students=user) |
            Course.objects.filter(teacher=user)
        )
        serializer = CourseSerializer(courses.distinct(), many=True)
        return Response(serializer.data)

    # GET /api/courses/{id}/lessons/
    @action(methods=["GET"], detail=True)
    def lessons(self, request, pk=None):
        course = self.get_object()
        lessons = course.lessons.all()
        serializer = LessonSerializer(lessons, many=True)
        return Response(serializer.data)

    # GET /api/courses/{id}/progress/
    @action(methods=["GET"], detail=True)
    def progress(self, request, pk=None):
        course = self.get_object()
        student = request.user

        lessons_count = course.lessons.count()
        completed_count = Progress.objects.filter(
            student=student,
            lesson__course=course,
            completed=True
        ).count()

        percent = (completed_count / lessons_count * 100) if lessons_count > 0 else 0

        return Response({
            "course": course.id,
            "progress": round(percent, 2),
            "completed_lessons": completed_count,
            "total_lessons": lessons_count,
        })

    # GET /api/courses/popular/
    @action(methods=["GET"], detail=False)
    def popular(self, request):
        courses = (
            Course.objects
            .annotate(students_count=Count("enrollments"))
            .order_by("-students_count")[:5]
        )
        serializer = CourseSerializer(courses, many=True)
        return Response(serializer.data)

    # GET /api/courses/free/
    @action(methods=["GET"], detail=False)
    def free(self, request):
        courses = Course.objects.filter(price=0)
        serializer = CourseSerializer(courses, many=True)
        return Response(serializer.data)

    # Q-запрос
    # Курсы с уровнем "beginner" И категорией "programming" И ценой до 5000 ИЛИ с количеством студентов более 100 и неопубликованные
    @action(methods=["GET"], detail=False)
    def q_courses_complex(self, request):
        courses = (
            Course.objects
            .annotate(students_count=Count("enrollments"))
            .filter(
                (
                    Q(level="beginner", category="programming", price__lte=5000)
                    |
                    Q(students_count__gt=100)
                )
                &
                ~Q(published=True)
            )
        )

        serializer = CourseSerializer(courses, many=True)
        return Response(serializer.data)


class LessonViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer

    filter_backends = [OrderingFilter, SearchFilter]
    search_fields = ["name", "description"]
    ordering_fields = ["serial_number"]
    ordering = ["serial_number"]


class AssignmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Assignment.objects.all()
    serializer_class = AssignmentSerializer


class SubmissionViewSet(viewsets.ModelViewSet):
    queryset = Submission.objects.all()
    serializer_class = SubmissionSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_fields = {
        "status": ["exact"],
        "assignment": ["exact"],
    }

    # GET /api/submissions/my/
    @action(methods=["GET"], detail=False)
    def my(self, request):
        subs = Submission.objects.filter(student=request.user)
        serializer = SubmissionSerializer(subs, many=True)
        return Response(serializer.data)

    # PATCH /api/submissions/{id}/grade/
    @action(methods=["PATCH"], detail=True)
    def grade(self, request, pk=None):
        submission = self.get_object()

        if submission.assignment.lesson.course.teacher != request.user:
            return Response(
                {"detail": "Только преподаватель курса может ставить оценки."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(submission, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(status="checked")
        return Response(serializer.data)

    # Q-запрос
    # Решения заданий со статусом "pending" И оценкой выше 80 ИЛИ отправленные в последние 7 дней И НЕ оцененные
    @action(methods=["GET"], detail=False)
    def q_submissions_complex(self, request):
        seven_days_ago = timezone.now() - timedelta(days=7)

        submissions = Submission.objects.filter(
            (
                Q(status="pending", score__gt=80)
                |
                Q(submitted_at__gte=seven_days_ago)
            )
            &
            ~Q(status="checked")
        )

        serializer = SubmissionSerializer(submissions, many=True)
        return Response(serializer.data)


class EnrollmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Enrollment.objects.all()
    serializer_class = EnrollmentSerializer


class ProgressViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProgressSerializer

    def get_queryset(self):
        return Progress.objects.filter(student=self.request.user)
