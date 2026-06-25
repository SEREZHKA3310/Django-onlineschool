from functools import wraps

from datetime import timedelta

from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Avg
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from .models import Course, Lesson, Assignment, Submission, Enrollment, Progress
from .permissions import user_owns_course

User = get_user_model()


def _parse_due_date(value):
    dt = parse_datetime(value)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def staff_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect("courses_list")
        return view_func(request, *args, **kwargs)
    return wrapper


def home(request):
    context = {"is_staff": request.user.is_authenticated and request.user.is_staff}
    if context["is_staff"]:
        context["pending_count"] = Submission.objects.filter(status="pending").count()
        context["courses_count"] = Course.objects.count()
        context["students_count"] = Enrollment.objects.values("student").distinct().count()
    elif request.user.is_authenticated:
        context["my_enrollments"] = Enrollment.objects.filter(
            student=request.user,
        ).select_related("course")[:5]
    return render(request, "courses/home.html", context)


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    error = None
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username", ""),
            password=request.POST.get("password", ""),
        )
        if user is not None:
            login(request, user)
            return redirect("home")
        error = "Неверный логин или пароль."
    return render(request, "courses/login.html", {"error": error})


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        password2 = request.POST.get("password2", "")
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()

        if not username or not password:
            error = "Заполните логин и пароль."
        elif password != password2:
            error = "Пароли не совпадают."
        elif User.objects.filter(username=username).exists():
            error = "Пользователь с таким логином уже существует."
        else:
            user = User.objects.create_user(
                username=username,
                password=password,
                email=email,
                first_name=first_name,
                role="student",
            )
            login(request, user)
            return redirect("home")

    return render(request, "courses/register.html", {"error": error})


def logout_view(request):
    logout(request)
    return redirect("home")


def courses_list(request):
    qs = Course.objects.select_related("teacher").annotate(
        students_count=Count("enrollments"),
    )
    if not (request.user.is_authenticated and request.user.is_staff):
        qs = qs.filter(published=True)

    level = request.GET.get("level")
    category = request.GET.get("category")
    search = request.GET.get("search")
    if level:
        qs = qs.filter(level=level)
    if category:
        qs = qs.filter(category=category)
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))

    enrolled_ids = set()
    if request.user.is_authenticated:
        enrolled_ids = set(
            Enrollment.objects.filter(student=request.user).values_list("course_id", flat=True)
        )

    return render(request, "courses/courses_list.html", {
        "courses": qs,
        "enrolled_ids": enrolled_ids,
        "filters": {"level": level, "category": category, "search": search},
    })


def course_detail(request, pk):
    course = get_object_or_404(Course.objects.select_related("teacher"), pk=pk)
    if not course.published and not request.user.is_staff:
        return redirect("courses_list")

    lessons = course.lessons.prefetch_related("assignments").all()
    is_enrolled = False
    enrollment = None
    completed_lesson_ids = set()
    progress_percent = 0

    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(student=request.user, course=course).first()
        is_enrolled = enrollment is not None
        if is_enrolled:
            completed_lesson_ids = set(
                Progress.objects.filter(
                    student=request.user, lesson__course=course, completed=True,
                ).values_list("lesson_id", flat=True)
            )
            total = lessons.count()
            progress_percent = round(len(completed_lesson_ids) / total * 100, 1) if total else 0

    return render(request, "courses/course_detail.html", {
        "course": course,
        "lessons": lessons,
        "is_enrolled": is_enrolled,
        "enrollment": enrollment,
        "completed_lesson_ids": completed_lesson_ids,
        "progress_percent": progress_percent,
    })


@login_required
@require_POST
def course_enroll(request, pk):
    course = get_object_or_404(Course, pk=pk, published=True)
    if not Enrollment.objects.filter(student=request.user, course=course).exists():
        Enrollment.objects.create(student=request.user, course=course)
    return redirect("course_detail", pk=pk)


@login_required
def my_courses(request):
    enrollments = Enrollment.objects.filter(
        student=request.user,
    ).select_related("course").order_by("-enrolled_at")
    return render(request, "courses/my_courses.html", {"enrollments": enrollments})


@login_required
@require_POST
def lesson_complete(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if not Enrollment.objects.filter(student=request.user, course=lesson.course).exists():
        return redirect("course_detail", pk=lesson.course_id)

    progress, _ = Progress.objects.get_or_create(student=request.user, lesson=lesson)
    if not progress.completed:
        progress.completed = True
        progress.completed_at = timezone.now()
        progress.save()
    Enrollment.recalculate_progress(request.user, lesson.course)
    return redirect("course_detail", pk=lesson.course_id)


@login_required
def my_submissions(request):
    submissions = Submission.objects.filter(
        student=request.user,
    ).select_related("assignment", "assignment__lesson", "assignment__lesson__course")
    return render(request, "courses/my_submissions.html", {"submissions": submissions})


@login_required
def submit_assignment(request, pk):
    assignment = get_object_or_404(
        Assignment.objects.select_related("lesson", "lesson__course"), pk=pk,
    )
    course = assignment.lesson.course
    if not Enrollment.objects.filter(student=request.user, course=course).exists():
        return redirect("courses_list")

    existing = Submission.objects.filter(student=request.user, assignment=assignment).first()
    if existing and existing.status == "checked":
        return redirect("my_submissions")

    error = None
    if request.method == "POST":
        if existing:
            return redirect("my_submissions")

        answer = request.POST.get("answer", "").strip()
        if not answer:
            error = "Введите текст решения."
        else:
            Submission.objects.create(
                assignment=assignment,
                student=request.user,
                answer=answer,
                file=request.FILES.get("file"),
                status=assignment.resolve_submission_status(),
            )
            return redirect("my_submissions")

    return render(request, "courses/submit_assignment.html", {
        "assignment": assignment,
        "existing": existing,
        "error": error,
    })


@staff_required
def course_create(request):
    if request.method == "POST":
        course = Course.objects.create(
            name=request.POST["name"],
            description=request.POST.get("description", ""),
            price=int(request.POST["price"]),
            level=request.POST["level"],
            category=request.POST["category"],
            duration=int(request.POST["duration"]),
            unit_of_time=request.POST["unit_of_time"],
            image=request.FILES["image"],
            published=request.POST.get("published") == "on",
            teacher=request.user,
        )
        return redirect("course_detail", pk=course.pk)
    return render(request, "courses/course_form.html")


@staff_required
def course_update(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if not user_owns_course(request.user, course):
        return redirect("courses_list")
    if request.method == "POST":
        course.name = request.POST["name"]
        course.description = request.POST.get("description", "")
        course.price = int(request.POST["price"])
        course.level = request.POST["level"]
        course.category = request.POST["category"]
        course.duration = int(request.POST["duration"])
        course.unit_of_time = request.POST["unit_of_time"]
        course.published = request.POST.get("published") == "on"
        if request.FILES.get("image"):
            course.image = request.FILES["image"]
        course.save()
        return redirect("course_detail", pk=course.pk)
    return render(request, "courses/course_form.html", {"course": course})


@staff_required
def course_delete(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if not user_owns_course(request.user, course):
        return redirect("courses_list")
    if request.method == "POST":
        course.delete()
        return redirect("courses_list")
    return render(request, "courses/course_confirm_delete.html", {"course": course})


@staff_required
def lesson_create(request, course_pk):
    course = get_object_or_404(Course, pk=course_pk)
    if not user_owns_course(request.user, course):
        return redirect("courses_list")
    if request.method == "POST":
        Lesson.objects.create(
            course=course,
            name=request.POST["name"],
            description=request.POST.get("description", ""),
            content=request.POST.get("content", ""),
            link_to_video=request.POST.get("link_to_video") or None,
            duration=request.POST["duration"],
            serial_number=int(request.POST["serial_number"]),
        )
        return redirect("course_detail", pk=course.pk)
    return render(request, "courses/lesson_form.html", {"course": course})


@staff_required
def lesson_update(request, pk):
    lesson = get_object_or_404(Lesson.objects.select_related("course"), pk=pk)
    if not user_owns_course(request.user, lesson.course):
        return redirect("courses_list")
    if request.method == "POST":
        lesson.name = request.POST["name"]
        lesson.description = request.POST.get("description", "")
        lesson.content = request.POST.get("content", "")
        lesson.link_to_video = request.POST.get("link_to_video") or None
        lesson.duration = request.POST["duration"]
        lesson.serial_number = int(request.POST["serial_number"])
        lesson.save()
        return redirect("course_detail", pk=lesson.course_id)
    return render(request, "courses/lesson_form.html", {"course": lesson.course, "lesson": lesson})


@staff_required
def lesson_delete(request, pk):
    lesson = get_object_or_404(Lesson.objects.select_related("course"), pk=pk)
    if not user_owns_course(request.user, lesson.course):
        return redirect("courses_list")
    course = lesson.course
    if request.method == "POST":
        lesson.delete()
        return redirect("course_detail", pk=course.pk)
    return render(request, "courses/lesson_confirm_delete.html", {"lesson": lesson})


@staff_required
def assignment_create(request, lesson_pk):
    lesson = get_object_or_404(Lesson.objects.select_related("course"), pk=lesson_pk)
    if not user_owns_course(request.user, lesson.course):
        return redirect("courses_list")
    error = None
    if request.method == "POST":
        due_date = _parse_due_date(request.POST["due_date"])
        if due_date is None or due_date <= timezone.now():
            error = "Срок сдачи должен быть в будущем."
        else:
            Assignment.objects.create(
                lesson=lesson,
                name=request.POST["name"],
                description=request.POST.get("description", ""),
                max_score=int(request.POST["max_score"]),
                due_date=due_date,
            )
            return redirect("course_detail", pk=lesson.course_id)
    default_due = (timezone.now() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M")
    return render(request, "courses/assignment_form.html", {
        "lesson": lesson,
        "default_due": default_due,
        "error": error,
    })


@staff_required
def assignment_update(request, pk):
    assignment = get_object_or_404(
        Assignment.objects.select_related("lesson", "lesson__course"), pk=pk,
    )
    if not user_owns_course(request.user, assignment.lesson.course):
        return redirect("courses_list")
    error = None
    if request.method == "POST":
        due_date = _parse_due_date(request.POST["due_date"])
        if due_date is None or due_date <= timezone.now():
            error = "Срок сдачи должен быть в будущем."
        else:
            assignment.due_date = due_date
            assignment.name = request.POST["name"]
            assignment.description = request.POST.get("description", "")
            assignment.max_score = int(request.POST["max_score"])
            assignment.save()
            return redirect("course_detail", pk=assignment.lesson.course_id)
    due_local = assignment.due_date.strftime("%Y-%m-%dT%H:%M")
    return render(request, "courses/assignment_form.html", {
        "lesson": assignment.lesson,
        "assignment": assignment,
        "default_due": due_local,
        "error": error,
    })


@staff_required
def assignment_delete(request, pk):
    assignment = get_object_or_404(
        Assignment.objects.select_related("lesson", "lesson__course"), pk=pk,
    )
    if not user_owns_course(request.user, assignment.lesson.course):
        return redirect("courses_list")
    course = assignment.lesson.course
    if request.method == "POST":
        assignment.delete()
        return redirect("course_detail", pk=course.pk)
    return render(request, "courses/assignment_confirm_delete.html", {"assignment": assignment})


@staff_required
def submissions_list(request):
    qs = Submission.objects.select_related(
        "student", "assignment", "assignment__lesson", "assignment__lesson__course",
    ).filter(assignment__lesson__course__teacher=request.user)
    status_filter = request.GET.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(request, "courses/submissions_list.html", {
        "submissions": qs.order_by("-submitted_at"),
        "status_filter": status_filter,
        "status_choices": Submission.status_choices,
    })


@staff_required
def submission_grade(request, pk):
    submission = get_object_or_404(
        Submission.objects.select_related(
            "student", "assignment", "assignment__lesson", "assignment__lesson__course",
        ).filter(assignment__lesson__course__teacher=request.user),
        pk=pk,
    )
    error = None
    if request.method == "POST":
        score = request.POST.get("score")
        comment = request.POST.get("teacher_comment", "")
        if score is None or score == "":
            error = "Укажите оценку."
        else:
            score = int(score)
            if score > submission.assignment.max_score:
                error = f"Оценка не может превышать {submission.assignment.max_score}."
            elif score < 0:
                error = "Оценка не может быть отрицательной."
            else:
                submission.score = score
                submission.teacher_comment = comment
                submission.status = "checked"
                submission.save()
                return redirect("submissions_list")
    return render(request, "courses/submission_grade.html", {
        "submission": submission,
        "error": error,
    })


@staff_required
def analytics(request):
    popular = (
        Course.objects
        .annotate(
            students_count=Count("enrollments"),
            average_score=Avg(
                "lessons__assignments__submissions__score",
                filter=Q(lessons__assignments__submissions__status="checked"),
            ),
        )
        .order_by("-students_count")[:10]
    )
    overdue = Assignment.objects.filter(
        due_date__lt=timezone.now(),
    ).select_related("lesson", "lesson__course")[:10]
    return render(request, "courses/analytics.html", {
        "popular_courses": popular,
        "overdue_assignments": overdue,
    })
