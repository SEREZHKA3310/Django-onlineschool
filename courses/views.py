"""
REST API представления онлайн-школы: курсы, уроки, задания, решения, прогресс.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import Avg, Count, Q, QuerySet
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from .models import Assignment, Course, Enrollment, Lesson, Progress, Submission
from .permissions import IsStaffUser
from .serializers import (
    AssignmentSerializer,
    CourseSerializer,
    EnrollmentSerializer,
    LessonSerializer,
    ProgressSerializer,
    SubmissionSerializer,
)
User = get_user_model()


def annotate_courses(qs: QuerySet[Course]) -> QuerySet[Course]:
    """
    Добавляет аннотации students_count, lessons_count и average_score к queryset курсов.

    Args:
        qs: Базовый queryset модели Course.

    Returns:
        Queryset с агрегированной статистикой по записям, урокам и оценкам.
    """
    return qs.annotate(
        students_count=Count("enrollments"),
        lessons_count=Count("lessons", distinct=True),
        average_score=Avg(
            "lessons__assignments__submissions__score",
            filter=Q(lessons__assignments__submissions__status="checked"),
        ),
    )


class CourseViewSet(viewsets.ModelViewSet):
    """CRUD курсов, запись студентов, прогресс и аналитические action-методы."""

    serializer_class = CourseSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = {
        "level": ["exact"],
        "category": ["exact"],
        "teacher": ["exact"],
        "published": ["exact"],
        "price": ["gte", "lte", "exact"],
    }
    search_fields = ["name", "description"]
    ordering_fields = ["price", "created_at"]
    ordering = ["-created_at"]

    def get_permissions(self) -> list[BasePermission]:
        """Права: изменение курса — только staff; чтение — для всех."""
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsStaffUser()]
        return [AllowAny()]

    def get_queryset(self) -> QuerySet[Course]:
        """Курсы с аннотациями; студентам — только опубликованные."""
        qs = annotate_courses(Course.objects.select_related("teacher"))
        user = self.request.user
        if user.is_authenticated and user.is_staff:
            return qs
        return qs.filter(published=True)

    def perform_update(self, serializer: BaseSerializer) -> None:
        """
        Обновляет курс только если текущий пользователь — его преподаватель.

        Args:
            serializer: Сериализатор с instance курса.
        """
        if serializer.instance.teacher_id != self.request.user.id:
            raise PermissionDenied("Можно изменять только свои курсы.")
        serializer.save()

    def perform_destroy(self, instance: Course) -> None:
        """
        Удаляет курс только владельцем (преподавателем).

        Args:
            instance: Удаляемый курс.
        """
        if instance.teacher_id != self.request.user.id:
            raise PermissionDenied("Можно удалять только свои курсы.")
        instance.delete()

    def get_serializer_context(self) -> dict[str, Any]:
        """Добавляет список id курсов, на которые записан текущий пользователь."""
        context = super().get_serializer_context()
        request = self.request
        if request.user.is_authenticated:
            context["enrolled_courses"] = list(
                Enrollment.objects.filter(student=request.user).values_list("course_id", flat=True)
            )
        else:
            context["enrolled_courses"] = []
        return context

    def perform_create(self, serializer: BaseSerializer) -> None:
        """
        Создаёт курс с привязкой к текущему преподавателю.

        Args:
            serializer: Валидированный сериализатор курса.
        """
        teacher = self.request.user
        if not teacher.is_authenticated or not teacher.is_staff:
            teacher = User.objects.filter(is_staff=True).first() or User.objects.first()
        serializer.save(teacher=teacher)

    @action(methods=["POST"], detail=True, permission_classes=[IsAuthenticated])
    def enroll(self, request: Request, pk: str | None = None) -> Response:
        """
        Записывает текущего студента на курс.

        Args:
            request: HTTP-запрос.
            pk: Первичный ключ курса.

        Returns:
            Ответ с сообщением об успехе или ошибке дублирования.
        """
        course = self.get_object()
        student = request.user

        if Enrollment.objects.filter(student=student, course=course).exists():
            return Response(
                {"detail": "Вы уже записаны на этот курс."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            Enrollment.objects.create(student=student, course=course)
        except IntegrityError:
            return Response(
                {"detail": "Вы уже записаны на этот курс."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": "Вы успешно записались на курс."})

    @action(methods=["GET"], detail=True)
    def lessons(self, request: Request, pk: str | None = None) -> Response:
        """
        Возвращает список уроков курса с флагом is_completed.

        Args:
            request: HTTP-запрос.
            pk: Первичный ключ курса.

        Returns:
            JSON-список уроков.
        """
        course = self.get_object()
        lessons = course.lessons.all()
        context = self.get_serializer_context()
        if request.user.is_authenticated:
            context["completed_lessons"] = list(
                Progress.objects.filter(
                    student=request.user, lesson__course=course, completed=True,
                ).values_list("lesson_id", flat=True)
            )
        else:
            context["completed_lessons"] = []
        serializer = LessonSerializer(lessons, many=True, context=context)
        return Response(serializer.data)

    @action(methods=["GET"], detail=True, permission_classes=[IsAuthenticated])
    def progress(self, request: Request, pk: str | None = None) -> Response:
        """
        Возвращает процент прогресса студента по курсу.

        Args:
            request: HTTP-запрос.
            pk: Первичный ключ курса.

        Returns:
            Словарь с progress, completed_lessons и total_lessons.
        """
        course = self.get_object()
        student = request.user

        lessons_count = course.lessons.count()
        completed_count = Progress.objects.filter(
            student=student,
            lesson__course=course,
            completed=True,
        ).count()

        percent = (completed_count / lessons_count * 100) if lessons_count > 0 else 0

        return Response({
            "course": course.id,
            "progress": round(percent, 2),
            "completed_lessons": completed_count,
            "total_lessons": lessons_count,
        })

    @action(methods=["GET"], detail=False)
    def popular(self, request: Request) -> Response:
        """
        Топ-5 популярных курсов по числу записей.

        Args:
            request: HTTP-запрос.

        Returns:
            Список курсов с аннотациями.
        """
        courses = (
            annotate_courses(Course.objects.select_related("teacher"))
            .order_by("-students_count")[:5]
        )
        serializer = CourseSerializer(courses, many=True, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(methods=["GET"], detail=False)
    def free(self, request: Request) -> Response:
        """
        Список бесплатных курсов (price=0).

        Args:
            request: HTTP-запрос.

        Returns:
            Список курсов.
        """
        courses = self.get_queryset().filter(price=0)
        serializer = CourseSerializer(courses, many=True)
        return Response(serializer.data)

    @action(methods=["GET"], detail=False)
    def q_courses_complex(self, request: Request) -> Response:
        """
        Сложная выборка курсов (beginner+programming или >100 студентов).

        Args:
            request: HTTP-запрос.

        Returns:
            Отфильтрованный список курсов.
        """
        courses = self.get_queryset().filter(
            (
                Q(level="beginner", category="programming", price__lte=5000)
                | Q(students_count__gt=100)
            )
            & Q(published=True)
            & ~Q(price=0)
        )
        serializer = CourseSerializer(courses, many=True)
        return Response(serializer.data)


class LessonViewSet(viewsets.ModelViewSet):
    """CRUD уроков и отметка урока пройденным."""

    serializer_class = LessonSerializer
    filter_backends = [OrderingFilter, SearchFilter]
    search_fields = ["name", "description"]
    ordering_fields = ["serial_number"]
    ordering = ["serial_number"]

    def get_serializer_context(self) -> dict[str, Any]:
        """Передаёт в сериализатор id пройденных уроков текущего студента."""
        context = super().get_serializer_context()
        request = self.request
        if request.user.is_authenticated:
            context["completed_lessons"] = list(
                Progress.objects.filter(
                    student=request.user, completed=True,
                ).values_list("lesson_id", flat=True)
            )
        else:
            context["completed_lessons"] = []
        return context

    def get_permissions(self) -> list[BasePermission]:
        """Изменение и complete — аутентифицированные; чтение — для всех."""
        if self.action in ("create", "update", "partial_update", "destroy", "complete"):
            return [IsAuthenticated()]
        return [AllowAny()]

    def get_queryset(self) -> QuerySet[Lesson]:
        """Уроки с учётом роли: staff — свои курсы; студент — записанные и опубликованные."""
        qs = Lesson.objects.select_related("course", "course__teacher")
        course_id = self.request.query_params.get("course_id")
        if course_id is not None:
            qs = qs.filter(course_id=course_id)

        user = self.request.user
        if user.is_authenticated and user.is_staff:
            return qs.filter(course__teacher=user)

        qs = qs.filter(course__published=True)
        if user.is_authenticated:
            enrolled_course_ids = Enrollment.objects.filter(
                student=user,
            ).values_list("course_id", flat=True)
            return qs.filter(
                Q(course_id__in=enrolled_course_ids) | Q(course__published=True)
            )
        return qs

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Создание урока — только для staff."""
        if not request.user.is_staff:
            return Response(
                {"detail": "Только администратор может создавать уроки."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)

    def _deny_if_not_lesson_owner(self, lesson: Lesson) -> Response | None:
        """
        Проверяет владение курсом урока.

        Args:
            lesson: Урок для проверки.

        Returns:
            Response 403 или None, если доступ разрешён.
        """
        if lesson.course.teacher_id != self.request.user.id:
            return Response(
                {"detail": "Можно управлять уроками только своих курсов."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Полное обновление урока с проверкой владельца курса."""
        if not request.user.is_staff:
            return Response(
                {"detail": "Только администратор может изменять уроки."},
                status=status.HTTP_403_FORBIDDEN,
            )
        lesson = self.get_object()
        denied = self._deny_if_not_lesson_owner(lesson)
        if denied:
            return denied
        return super().update(request, *args, **kwargs)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Частичное обновление урока с проверкой владельца курса."""
        if not request.user.is_staff:
            return Response(
                {"detail": "Только администратор может изменять уроки."},
                status=status.HTTP_403_FORBIDDEN,
            )
        lesson = self.get_object()
        denied = self._deny_if_not_lesson_owner(lesson)
        if denied:
            return denied
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Удаление урока с проверкой владельца курса."""
        if not request.user.is_staff:
            return Response(
                {"detail": "Только администратор может удалять уроки."},
                status=status.HTTP_403_FORBIDDEN,
            )
        lesson = self.get_object()
        denied = self._deny_if_not_lesson_owner(lesson)
        if denied:
            return denied
        return super().destroy(request, *args, **kwargs)

    @action(methods=["GET"], detail=False, url_path="course/(?P<course_id>[^/.]+)")
    def by_course(self, request: Request, course_id: str | None = None) -> Response:
        """
        Уроки конкретного курса.

        Args:
            request: HTTP-запрос.
            course_id: Id курса из URL.

        Returns:
            Список уроков.
        """
        lessons = self.get_queryset().filter(course_id=course_id)
        serializer = self.get_serializer(lessons, many=True)
        return Response(serializer.data)

    @action(methods=["POST"], detail=True)
    def complete(self, request: Request, pk: str | None = None) -> Response:
        """
        Отмечает урок пройденным и пересчитывает Enrollment.progress.

        Args:
            request: HTTP-запрос.
            pk: Id урока.

        Returns:
            Ответ с новым процентом прогресса по курсу.
        """
        lesson = self.get_object()
        student = request.user

        if not Enrollment.objects.filter(student=student, course=lesson.course).exists():
            return Response(
                {"detail": "Вы не записаны на этот курс."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        progress, _ = Progress.objects.get_or_create(student=student, lesson=lesson)
        if not progress.completed:
            progress.completed = True
            progress.completed_at = timezone.now()
            progress.save()

        Enrollment.recalculate_progress(student, lesson.course)

        enrollment = Enrollment.objects.get(student=student, course=lesson.course)
        return Response({
            "detail": "Урок отмечен как пройденный.",
            "lesson": lesson.id,
            "course_progress": float(enrollment.progress),
        })


class AssignmentViewSet(viewsets.ModelViewSet):
    """CRUD заданий к урокам."""

    serializer_class = AssignmentSerializer

    def get_serializer_context(self) -> dict[str, Any]:
        """Передаёт id заданий, по которым студент уже отправил решение."""
        context = super().get_serializer_context()
        request = self.request
        if request.user.is_authenticated:
            context["submitted_assignments"] = list(
                Submission.objects.filter(student=request.user).values_list("assignment_id", flat=True)
            )
        else:
            context["submitted_assignments"] = []
        return context

    def get_permissions(self) -> list[BasePermission]:
        """Изменение — staff; чтение — с ограничением по записи на курс."""
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsStaffUser()]
        return [AllowAny()]

    def get_queryset(self) -> QuerySet[Assignment]:
        """Задания: staff — свои курсы; студент — записанные опубликованные курсы."""
        qs = Assignment.objects.select_related("lesson", "lesson__course", "lesson__course__teacher")
        user = self.request.user

        if user.is_authenticated and user.is_staff:
            return qs.filter(lesson__course__teacher=user)

        qs = qs.filter(lesson__course__published=True)
        if user.is_authenticated:
            enrolled_course_ids = Enrollment.objects.filter(
                student=user,
            ).values_list("course_id", flat=True)
            return qs.filter(lesson__course_id__in=enrolled_course_ids)
        return qs.none()

    @action(methods=["GET"], detail=False)
    def overdue(self, request: Request) -> Response:
        """
        Просроченные задания преподавателя (due_date в прошлом).

        Args:
            request: HTTP-запрос.

        Returns:
            Список заданий.
        """
        if not request.user.is_staff:
            return Response(
                {"detail": "Доступ только для администратора."},
                status=status.HTTP_403_FORBIDDEN,
            )
        assignments = self.get_queryset().filter(due_date__lt=timezone.now())
        serializer = self.get_serializer(assignments, many=True)
        return Response(serializer.data)


class SubmissionViewSet(viewsets.ModelViewSet):
    """Отправка и проверка решений студентов."""

    serializer_class = SubmissionSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {
        "status": ["exact"],
        "assignment": ["exact"],
    }

    def get_permissions(self) -> list[BasePermission]:
        """Создание — студент; оценка — staff; список — по роли."""
        if self.action in ("create", "my"):
            return [IsAuthenticated()]
        if self.action in ("update", "partial_update", "destroy", "grade"):
            return [IsStaffUser()]
        return [IsAuthenticated()]

    def get_queryset(self) -> QuerySet[Submission]:
        """Staff видит решения своих курсов; студент — только свои."""
        qs = Submission.objects.select_related(
            "assignment",
            "assignment__lesson",
            "assignment__lesson__course",
            "student",
        )
        user = self.request.user

        if user.is_staff:
            return qs.filter(assignment__lesson__course__teacher=user)

        return qs.filter(student=user)

    def perform_create(self, serializer: BaseSerializer) -> None:
        """
        Создаёт решение с автоматическим статусом pending/late.

        Args:
            serializer: Валидированный сериализатор решения.
        """
        assignment = serializer.validated_data["assignment"]
        submission_status = assignment.resolve_submission_status()
        serializer.save(student=self.request.user, status=submission_status)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Полное обновление решения (оценка преподавателем курса)."""
        return super().update(request, *args, **kwargs)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Частичное обновление решения."""
        return super().partial_update(request, *args, **kwargs)

    @action(methods=["GET"], detail=False)
    def my(self, request: Request) -> Response:
        """
        Список решений текущего студента.

        Args:
            request: HTTP-запрос.

        Returns:
            JSON-список submissions.
        """
        subs = self.get_queryset().filter(student=request.user)
        serializer = self.get_serializer(subs, many=True)
        return Response(serializer.data)

    @action(methods=["PATCH"], detail=True)
    def grade(self, request: Request, pk: str | None = None) -> Response:
        """
        Выставляет оценку и переводит решение в статус checked.

        Args:
            request: HTTP-запрос с score и teacher_comment.
            pk: Id решения.

        Returns:
            Обновлённое решение.
        """
        submission = self.get_object()
        serializer = self.get_serializer(submission, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(status="checked")
        return Response(serializer.data)

    @action(methods=["GET"], detail=False)
    def late(self, request: Request) -> Response:
        """
        Просроченные работы (status=late) по курсам текущего преподавателя.

        Args:
            request: HTTP-запрос.

        Returns:
            Список просроченных решений.
        """
        if not request.user.is_staff:
            return Response(
                {"detail": "Доступ только для преподавателя."},
                status=status.HTTP_403_FORBIDDEN,
            )
        submissions = self.get_queryset().filter(status="late")
        serializer = self.get_serializer(submissions, many=True)
        return Response(serializer.data)

    @action(methods=["GET"], detail=False)
    def q_submissions_complex(self, request: Request) -> Response:
        """
        Сложная выборка решений для аналитики (staff).

        Args:
            request: HTTP-запрос.

        Returns:
            Отфильтрованный список решений.
        """
        if not request.user.is_staff:
            return Response(
                {"detail": "Доступ только для администратора."},
                status=status.HTTP_403_FORBIDDEN,
            )

        seven_days_ago = timezone.now() - timedelta(days=7)
        submissions = self.get_queryset().filter(
            (
                Q(status="pending") & Q(score__gt=80)
                | Q(submitted_at__gte=seven_days_ago)
            )
            & ~Q(status="checked")
        )
        serializer = self.get_serializer(submissions, many=True)
        return Response(serializer.data)


class EnrollmentViewSet(viewsets.ReadOnlyModelViewSet):
    """Просмотр записей на курсы (свои или все для staff)."""

    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Enrollment]:
        """
        Queryset записей: staff — все; студент — только свои.

        Returns:
            Queryset Enrollment с select_related.
        """
        qs = Enrollment.objects.select_related("student", "course")
        user = self.request.user
        if user.is_staff:
            return qs
        return qs.filter(student=user)


class ProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """Прогресс текущего студента по урокам."""

    serializer_class = ProgressSerializer

    def get_queryset(self) -> QuerySet[Progress]:
        """
        Прогресс только для аутентифицированного студента.

        Returns:
            Queryset Progress с select_related lesson и course.
        """
        return Progress.objects.select_related(
            "lesson", "lesson__course",
        ).filter(student=self.request.user)
