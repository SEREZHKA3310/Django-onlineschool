"""Management-команда: создание демо-пользователей admin и student."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

User = get_user_model()


class Command(BaseCommand):
    """Создаёт или обновляет учётные записи admin/admin и student/student с токенами API."""

    help = "Создаёт демо-пользователей admin/admin и student/student"

    def handle(self, *args: Any, **options: Any) -> None:
        """
        Создаёт преподавателя и студента с паролями и DRF-токенами.

        Args:
            *args: Позиционные аргументы команды.
            **options: Именованные опции команды.
        """
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@school.local",
                "first_name": "Админ",
                "role": "teacher",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            admin.set_password("admin")
            admin.save()
            Token.objects.get_or_create(user=admin)
            self.stdout.write(self.style.SUCCESS("Created admin / admin"))
        else:
            admin.is_staff = True
            admin.is_superuser = True
            admin.set_password("admin")
            admin.save()
            Token.objects.get_or_create(user=admin)
            self.stdout.write("Updated admin / admin")

        student, created = User.objects.get_or_create(
            username="student",
            defaults={
                "email": "student@school.local",
                "first_name": "Студент",
                "role": "student",
            },
        )
        if created:
            student.set_password("student")
            student.save()
            Token.objects.get_or_create(user=student)
            self.stdout.write(self.style.SUCCESS("Created student / student"))
        else:
            student.set_password("student")
            student.save()
            Token.objects.get_or_create(user=student)
            self.stdout.write("Updated student / student")
