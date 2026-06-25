"""Management-команда: топ популярных курсов по числу записей."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Count

from courses.models import Course


class Command(BaseCommand):
    """Выводит ТОП-5 курсов с наибольшим количеством записей студентов."""

    help = "Вывод самых популярных курсов (по количеству записей)"

    def handle(self, *args: Any, **options: Any) -> None:
        """
        Выполняет команду: печатает список курсов в stdout.

        Args:
            *args: Позиционные аргументы команды.
            **options: Именованные опции команды.
        """
        courses = (
            Course.objects
            .annotate(students_count=Count("enrollments"))
            .order_by("-students_count")[:5]
        )

        if not courses:
            self.stdout.write("Нет курсов для отображения")
            return

        self.stdout.write(self.style.SUCCESS("ТОП-5 самых популярных курсов:\n"))

        for course in courses:
            self.stdout.write(
                f"- {course.name} | "
                f"Уровень: {course.get_level_display()} | "
                f"Категория: {course.get_category_display()} | "
                f"Студентов: {course.students_count}"
            )
