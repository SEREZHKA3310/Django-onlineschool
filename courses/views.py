from datetime import timedelta

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from django.shortcuts import render, redirect, get_object_or_404

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
        teacher = self.request.user if self.request.user.is_authenticated else None

        if not teacher:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            teacher = User.objects.filter(role='teacher').first() or User.objects.first()

        serializer.save(teacher=teacher)

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
    # Курсы с уровнем "beginner" И категорией "programming" И ценой до 5000 ИЛИ с количеством студентов более 100 И опубликованные
    @action(methods=["GET"], detail=False)
    def q_courses_complex(self, request):
        courses = (
            Course.objects
            .annotate(students_count=Count("enrollments"))
            .filter(
                (
                    Q(level="beginner", category="programming", price__lte=5000)
                    | Q(students_count__gt=100)
                )
                & Q(published=True)
                & ~Q(price=0)
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

    def get_queryset(self):
        queryset = super().get_queryset()
        course_id = self.request.query_params.get('course_id', None)
        if course_id is not None:
            queryset = queryset.filter(course_id=course_id)
        return queryset

    @action(methods=["GET"], detail=False, url_path='course/(?P<course_id>[^/.]+)')
    def by_course(self, request, course_id=None):
        lessons = Lesson.objects.filter(course_id=course_id)
        serializer = self.get_serializer(lessons, many=True)
        return Response(serializer.data)


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
    # Решения заданий со статусом "pending" И оценкой выше 80 ИЛИ отправленные в последние 7 дней И НЕ проверенные
    @action(methods=["GET"], detail=False)
    def q_submissions_complex(self, request):
        seven_days_ago = timezone.now() - timedelta(days=7)

        submissions = Submission.objects.filter(
            (
                Q(status="pending")
                & Q(score__gt=80)
                | Q(submitted_at__gte=seven_days_ago)
            )
            & ~Q(status="checked")
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


def home(request):
    return render(request, 'courses/home.html')


def courses_list(request):
    courses = Course.objects.all()
    return render(request, 'courses/courses_list.html', {'courses': courses})


def course_create(request):
    if request.method == 'POST':
        from django.contrib.auth import get_user_model
        User = get_user_model()
        default_teacher = User.objects.filter(role='teacher').first()
        if not default_teacher:
            default_teacher = User.objects.first()
        if not default_teacher:
            default_teacher = User.objects.create_user(
                username='default_teacher',
                email='teacher@example.com',
                role='teacher'
            )

        Course.objects.create(
            name=request.POST['name'],
            description=request.POST.get('description', ''),
            price=int(request.POST['price']),
            level=request.POST['level'],
            category=request.POST['category'],
            duration=int(request.POST['duration']),
            unit_of_time=request.POST['unit_of_time'],
            image=request.FILES['image'],
            published=request.POST.get('published') == 'on',
            teacher=default_teacher
        )
        return redirect('courses_list')

    return render(request, 'courses/courses_form.html')


def course_update(request, pk):
    course = get_object_or_404(Course, pk=pk)

    if request.method == 'POST':
        course.name = request.POST['name']
        course.description = request.POST.get('description', '')
        course.price = int(request.POST['price'])
        course.level = request.POST['level']
        course.category = request.POST['category']
        course.duration = int(request.POST['duration'])
        course.unit_of_time = request.POST['unit_of_time']
        course.published = request.POST.get('published') == 'on'

        if 'image' in request.FILES and request.FILES['image']:
            course.image = request.FILES['image']

        course.save()
        return redirect('courses_list')

    return render(request, 'courses/courses_form.html', {'course': course})


def course_delete(request, pk):
    course = get_object_or_404(Course, pk=pk)
    course.delete()
    return redirect('courses_list')
