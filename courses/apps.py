from django.apps import AppConfig


class CoursesConfig(AppConfig):
    """Конфигурация приложения онлайн-школы (курсы, уроки, задания)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "courses"
    verbose_name = "Онлайн-школа"
