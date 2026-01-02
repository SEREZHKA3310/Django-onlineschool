from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

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

    filter_backends = [DjangoFilterBackend, OrderingFilter]

    filterset_fields = {
        "level": ["exact"],
        "category": ["exact"],
        "teacher": ["exact"],
        "published": ["exact"],
        "price": ["gte", "lte", "exact"],
    }

    ordering_fields = ["price", "created_at"]
    ordering = ["-created_at"]

    # POST /api/courses/ - создать курс (только для преподавателей)
    def perform_create(self, serializer):
        if not self.request.user.is_teacher:
            return Response(
                {"detail": "Только преподаватель может создавать курсы."},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer.save(teacher=self.request.user)

    # PUT /api/courses/{id}/ - обновить курс (только для преподавателя курса)
    def update(self, request, pk=None):
        course = self.get_object()
        if course.teacher != request.user:
            return Response({"detail": "Только преподаватель может обновить курс."},
                            status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(course, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    # PATCH /api/courses/{id}/ - частично обновить курс (только для преподавателя курса)
    def partial_update(self, request, pk=None):
        course = self.get_object()
        if course.teacher != request.user:
            return Response({"detail": "Только преподаватель может обновить курс."},
                            status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(course, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    # DELETE /api/courses/{id}/ - удалить курс (только для преподавателя курса)
    def destroy(self, request, pk=None):
        course = self.get_object()
        if course.teacher != request.user:
            return Response({"detail": "Только преподаватель может удалить курс."},
                            status=status.HTTP_403_FORBIDDEN)
        course.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # POST /api/courses/{id}/enroll/ - записаться на курс
    @action(methods=["POST"], detail=True)
    def enroll(self, request, pk=None):
        course = self.get_object()
        student = request.user

        if Enrollment.objects.filter(student=student, course=course).exists():
            return Response({"detail": "Вы уже записаны на этот курс."},
                            status=status.HTTP_400_BAD_REQUEST)

        Enrollment.objects.create(student=student, course=course)
        return Response({"detail": "Вы успешно записались на курс."}, status=status.HTTP_200_OK)

    # GET /api/courses/my/ - получить список моих курсов
    @action(methods=["GET"], detail=False)
    def my(self, request):
        user = request.user
        courses = Course.objects.filter(students=user) | Course.objects.filter(teacher=user)
        serializer = CourseSerializer(courses.distinct(), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # GET /api/courses/{id}/lessons/ - получить список уроков курса
    @action(methods=["GET"], detail=True)
    def lessons(self, request, pk=None):
        course = self.get_object()
        lessons = course.lessons.all()
        return Response(LessonSerializer(lessons, many=True).data, status=status.HTTP_200_OK)

    # GET /api/courses/{id}/progress/ - получить прогресс студента по курсу
    @action(methods=["GET"], detail=True)
    def progress(self, request, pk=None):
        course = self.get_object()
        student = request.user

        lessons_count = course.lessons.count()
        completed_count = Progress.objects.filter(
            student=student, lesson__course=course, completed=True
        ).count()

        percent = (completed_count / lessons_count * 100) if lessons_count > 0 else 0

        return Response({
            "course": course.id,
            "progress": round(percent, 2),
            "completed_lessons": completed_count,
            "total_lessons": lessons_count
        }, status=status.HTTP_200_OK)


class LessonViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer

    filter_backends = [OrderingFilter]
    ordering_fields = ["order"]
    ordering = ["order"]

    # GET /api/lessons/{id}/
    # (обычный retrieve — встроен в ReadOnlyModelViewSet)
    pass


class AssignmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Assignment.objects.all()
    serializer_class = AssignmentSerializer

    # GET /api/assignments/{id}/
    # (тоже встроен в ReadOnlyModelViewSet)
    pass


class SubmissionViewSet(viewsets.ModelViewSet):
    queryset = Submission.objects.all()
    serializer_class = SubmissionSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_fields = {
        "status": ["exact"],
        "assignment": ["exact"],
    }

    # GET /api/submissions/my/ - получить список решений студента
    @action(methods=["GET"], detail=False)
    def my(self, request):
        subs = Submission.objects.filter(student=request.user)
        return Response(SubmissionSerializer(subs, many=True).data, status=status.HTTP_200_OK)

    # PATCH /api/submissions/{id}/grade/ - оценить решение (только для преподавателя)
    @action(methods=["PATCH"], detail=True)
    def grade(self, request, pk=None):
        submission = self.get_object()
        teacher = request.user

        if submission.assignment.lesson.course.teacher != teacher:
            return Response({"detail": "Только преподаватель курса может ставить оценки."},
                            status=status.HTTP_403_FORBIDDEN)

        score = request.data.get("score")
        comment = request.data.get("teacher_comment")

        if score is not None:
            score = int(score)
            if score > submission.assignment.max_score:
                return Response({"detail": "Оценка не может превышать максимальный балл."},
                                status=status.HTTP_400_BAD_REQUEST)
            submission.score = score

        if comment:
            submission.teacher_comment = comment

        submission.status = "checked"
        submission.save()

        return Response(SubmissionSerializer(submission).data, status=status.HTTP_200_OK)


class EnrollmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Enrollment.objects.all()
    serializer_class = EnrollmentSerializer


class ProgressViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Progress.objects.all()
    serializer_class = ProgressSerializer

    # GET /api/progress/
    def get_queryset(self):
        return Progress.objects.filter(student=self.request.user)
