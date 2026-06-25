"""Management-команда: средняя цена опубликованных курсов."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Avg

from courses.models import Course


class Command(BaseCommand):
    """Вычисляет и выводит среднюю стоимость опубликованных курсов."""

    help = "Вычисляет среднюю стоимость всех опубликованных курсов"

    def handle(self, *args: Any, **options: Any) -> None:
        """
        Агрегирует Avg('price') по published=True и печатает результат.

        Args:
            *args: Позиционные аргументы команды.
            **options: Именованные опции команды.
        """
        result = Course.objects.filter(published=True).aggregate(Avg("price"))

        avg_price = result["price__avg"]

        if avg_price is not None:
            formatted_price = f"{avg_price:.2f}"
            self.stdout.write(
                self.style.SUCCESS(f"Средняя стоимость курса: {formatted_price}")
            )
        else:
            self.stdout.write(
                self.style.WARNING("Нет опубликованных курсов для расчета стоимости.")
            )
