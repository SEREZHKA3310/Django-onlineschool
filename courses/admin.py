from django.contrib import admin
from django.utils import timezone
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from simple_history.admin import SimpleHistoryAdmin
from import_export.formats import base_formats

from .models import (
    User, Course, Lesson, Assignment,
    Enrollment, Submission, Progress
)


class CourseResource(resources.ModelResource):
    students_count = fields.Field(column_name="Количество студентов")
    lessons_count = fields.Field(column_name="Количество уроков")
    average_rating = fields.Field(column_name="Средний рейтинг")
    teacher_display = fields.Field(column_name="Преподаватель")
    level_display = fields.Field(column_name="Уровень")
    category_display = fields.Field(column_name="Категория")

    class Meta:
        model = Course
        fields = (
            "name", "description", "level_display", "category_display",
            "price", "teacher_display", "students_count",
            "lessons_count", "average_rating", "created_at",
        )

    def get_export_queryset(self, request):
        return super().get_export_queryset(request).filter(published=True)

    def dehydrate_teacher_display(self, course):
        return f"{course.teacher.first_name} {course.teacher.last_name}".strip() or course.teacher.email

    def dehydrate_level_display(self, course):
        return course.get_level_display()

    def dehydrate_category_display(self, course):
        return course.get_category_display()

    def dehydrate_students_count(self, course):
        return course.students.count()

    def dehydrate_lessons_count(self, course):
        return course.lessons.count()

    def dehydrate_average_rating(self, course):
        scores = Submission.objects.filter(
            assignment__lesson__course=course,
            score__isnull=False
        ).values_list("score", flat=True)
        return round(sum(scores) / len(scores), 2) if scores else 0

    def dehydrate_price(self, course):
        return f"{course.price:,.2f} ₽"

    def dehydrate_created_at(self, course):
        return course.created_at.strftime("%d.%m.%Y")


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    readonly_fields = ("enrolled_at",)


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0


class SubmissionInline(admin.TabularInline):
    model = Submission
    extra = 0
    readonly_fields = ("submitted_at", "status")


@admin.register(Course)
class CourseAdmin(ImportExportModelAdmin, SimpleHistoryAdmin):
    resource_class = CourseResource

    def get_export_formats(self):
        return [base_formats.XLSX]

    list_display = ("id", "name", "price", "published", "level", "created_at", "lesson_count")
    list_display_links = ("name",)
    list_filter = ("published", "level", "category")
    search_fields = ("name", "description")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)
    inlines = [LessonInline]
    raw_id_fields = ('teacher',)

    @admin.display(description="Кол-во уроков")
    def lesson_count(self, obj):
        return obj.lessons.count()

    fieldsets = (
        ("Основная информация", {
            "fields": ("name", "description", "image")
        }),
        ("Параметры курса", {
            "fields": ("level", "category", "duration", "unit_of_time", "price")
        }),
        ("Публикация", {
            "fields": ("published", "teacher")
        }),
        ("Служебная информация", {
            "classes": ("collapse",),
            "fields": ("created_at",)
        }),
    )


@admin.register(Lesson)
class LessonAdmin(SimpleHistoryAdmin):
    list_display = ("id", "name", "course", "serial_number", "duration", "assignment_count")
    list_display_links = ("id", "name")
    list_filter = ("course", "duration")
    search_fields = ("name", "description")
    inlines = [AssignmentInline]

    @admin.display(description="Кол-во заданий")
    def assignment_count(self, obj):
        return obj.assignments.count()

    fieldsets = (
        ("Основное", {
            "fields": ("course", "name", "serial_number")
        }),
        ("Контент", {
            "fields": ("description", "content", "link_to_video", "duration")
        }),
    )


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "lesson", "max_score", "due_date", "is_overdue")
    list_display_links = ("id", "name")
    list_filter = ("lesson__course", "due_date")
    search_fields = ("name", "description")
    inlines = [SubmissionInline]

    @admin.display(description="Просрочено")
    def is_overdue(self, obj):
        if not obj.due_date:
            return False
        return obj.due_date < timezone.now()

    fieldsets = (
        ("Основное", {
            "fields": ("lesson", "name", "description")
        }),
        ("Оценивание", {
            "fields": ("max_score", "due_date")
        }),
    )


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "course", "enrolled_at", "progress", "completed_at")
    list_filter = ("course", "enrolled_at")
    search_fields = ("student__email", "course__name")
    readonly_fields = ("enrolled_at",)
    list_display_links = ("id", "student")

    fieldsets = (
        ("Запись на курс", {
            "fields": ("student", "course")
        }),
        ("Прогресс", {
            "fields": ("progress", "completed_at")
        }),
        ("Служебная информация", {
            "classes": ("collapse",),
            "fields": ("enrolled_at",)
        }),
    )


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "assignment", "student", "score", "status", "submitted_at")
    list_display_links = ("id", "status")
    list_filter = ("status", "submitted_at", "assignment__lesson__course")
    search_fields = ("student__email", "assignment__name")
    readonly_fields = ("submitted_at",)

    fieldsets = (
        ("Решение", {
            "fields": ("assignment", "student", "answer", "file")
        }),
        ("Проверка", {
            "fields": ("score", "teacher_comment", "status")
        }),
        ("Служебная информация", {
            "classes": ("collapse",),
            "fields": ("submitted_at",)
        }),
    )


@admin.register(Progress)
class ProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "student_name", "lesson", "completed", "completed_at")
    list_display_links = ("id", "lesson")
    list_filter = ("lesson__course", "completed")
    search_fields = ("student__email", "student__last_name")

    @admin.display(description="Студент")
    def student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"

    fieldsets = (
        ("Прогресс урока", {
            "fields": ("student", "lesson", "completed", "completed_at")
        }),
    )


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "first_name", "last_name", "role", "is_staff")
    list_filter = ("role", "is_staff", "is_active")
    search_fields = ("email", "first_name", "last_name")
    list_display_links = ("id", "email")

    fieldsets = (
        ("Основная информация", {
            "fields": ("email", "first_name", "last_name", "role")
        }),
        ("Доступ", {
            "classes": ("collapse",),
            "fields": ("is_active", "is_staff", "is_superuser")
        }),
    )
