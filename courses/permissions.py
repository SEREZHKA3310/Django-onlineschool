from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

if TYPE_CHECKING:
    from .models import Course, User


def user_owns_course(user: User, course: Course) -> bool:
    """
    Проверяет, что staff-пользователь является преподавателем курса.

    Args:
        user: Текущий пользователь.
        course: Курс для проверки владения.

    Returns:
        True, если пользователь — преподаватель данного курса.
    """
    return bool(
        user
        and user.is_authenticated
        and user.is_staff
        and course.teacher_id == user.id
    )


class IsStaffUser(BasePermission):
    """Разрешение для преподавателя (пользователь с is_staff=True)."""

    message = "Доступ только для администратора."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Проверяет, что пользователь аутентифицирован и имеет флаг staff.

        Args:
            request: HTTP-запрос DRF.
            view: Представление, к которому применяется проверка.

        Returns:
            True, если доступ разрешён.
        """
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
