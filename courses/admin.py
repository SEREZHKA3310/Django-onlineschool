from django.contrib import admin
from .models import User, Course, Lesson, Assignment, Enrollment, Submission, Progress
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin

class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1

class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 1


@admin.register(Course)
class CourseAdmin(SimpleHistoryAdmin):
    list_display = ("id", "name", "price", "published", "level", "created_at", "lesson_count")
    list_display_links = ("name",)
    list_filter = ("published", "level", "category")
    search_fields = ("name", "description")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)
    filter_horizontal = ("students",)
    inlines = [LessonInline]
    raw_id_fields = ('teacher',)
    

    @admin.display(description="Кол-во уроков")
    def lesson_count(self, obj):
        return obj.lessons.count()


@admin.register(Lesson)
class LessonAdmin(SimpleHistoryAdmin):
    list_display = ("id", "name", "course", "serial_number", "duration", "assignment_count")
    inlines = [AssignmentInline]

    @admin.display(description="Кол-во заданий")
    def assignment_count(self, obj):
        return obj.assignments.count()


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "lesson", "max_score", "due_date", "is_overdue")

    @admin.display(description="Просрочено")
    def is_overdue(self, obj):
        if not obj.due_date:
            return False
        return obj.due_date < timezone.now()


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "course", "enrolled_at", "progress", "completed_at")
    readonly_fields = ("enrolled_at",)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "assignment", "student", "score", "status", "submitted_at")
    list_filter = ("status", "submitted_at")


@admin.register(Progress)
class ProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "lesson", "completed", "completed_at")


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "first_name", "last_name")
    search_fields = ("email", "first_name", "last_name")
    list_display_links = ("email",)