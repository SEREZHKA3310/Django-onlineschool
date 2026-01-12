from django.core.management.base import BaseCommand
from django.db.models import Avg
from courses.models import Course


class Command(BaseCommand):
    help = "Вычисляет среднюю стоимость всех опубликованных курсов"

    def handle(self, *args, **options):
        result = Course.objects.filter(published=True).aggregate(Avg('price'))

        avg_price = result['price__avg']

        if avg_price is not None:
            formatted_price = f"{avg_price:.2f}"
            self.stdout.write(
                self.style.SUCCESS(f"Средняя стоимость курса: {formatted_price}")
            )
        else:
            self.stdout.write(
                self.style.WARNING("Нет опубликованных курсов для расчета стоимости.")
            )
