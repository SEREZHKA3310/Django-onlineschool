from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from .models import (
    Assignment,
    Course,
    Enrollment,
    Lesson,
    Progress,
    Submission,
    User,
)


class UserSerializer(serializers.ModelSerializer):
    """Сериализатор данных пользователя для вложенного отображения."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email"]


class CourseSerializer(serializers.ModelSerializer):
    """Сериализатор курса с аннотированной статистикой и флагом записи."""

    teacher = UserSerializer(read_only=True)
    is_enrolled = serializers.SerializerMethodField()
    students_count = serializers.IntegerField(read_only=True)
    lessons_count = serializers.IntegerField(read_only=True)
    average_score = serializers.FloatField(read_only=True, required=False)

    class Meta:
        model = Course
        fields = [
            "id", "name", "description", "price", "unit_of_time", "duration",
            "level", "category", "image", "published", "created_at", "teacher",
            "students", "is_enrolled", "students_count", "lessons_count", "average_score",
        ]
        read_only_fields = ("created_at", "teacher", "students")
        extra_kwargs = {
            "image": {"required": True, "allow_null": False},
        }

    def get_is_enrolled(self, obj: Course) -> bool:
        """
        Проверяет, записан ли текущий пользователь на курс.

        Args:
            obj: Объект курса.

        Returns:
            True, если id курса есть в context['enrolled_courses'].
        """
        enrolled_courses = self.context.get("enrolled_courses", [])
        return obj.id in enrolled_courses

    def validate_level(self, value: str) -> str:
        """
        Валидирует уровень сложности курса.

        Args:
            value: Код уровня.

        Returns:
            Проверенное значение уровня.

        Raises:
            ValidationError: Если уровень не из допустимого списка.
        """
        valid = ["beginner", "intermediate", "advanced"]
        if value not in valid:
            raise serializers.ValidationError(
                "Уровень должен быть beginner/intermediate/advanced."
            )
        return value

    def validate_category(self, value: str) -> str:
        """
        Валидирует категорию курса.

        Args:
            value: Код категории.

        Returns:
            Проверенное значение категории.

        Raises:
            ValidationError: Если категория не из допустимого списка.
        """
        valid = ["programming", "design", "marketing", "business"]
        if value not in valid:
            raise serializers.ValidationError(
                "Категория должна быть одной из: programming, design, marketing, business."
            )
        return value

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Валидирует цену (0–100 000 ₽) и положительную длительность.

        Args:
            data: Поля для создания или обновления курса.

        Returns:
            Проверенные данные.
        """
        price = data.get("price", self.instance.price if self.instance else None)
        if price is not None:
            if price < 0:
                raise serializers.ValidationError({"price": "Цена не может быть отрицательной."})
            if price > 100_000:
                raise serializers.ValidationError({"price": "Цена не может превышать 100 000 ₽."})

        duration = data.get("duration", self.instance.duration if self.instance else 1)
        if duration is not None and duration <= 0:
            raise serializers.ValidationError({"duration": "Длительность должна быть положительной."})
        return data


class LessonSerializer(serializers.ModelSerializer):
    """Сериализатор урока с флагом прохождения из context."""

    is_completed = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            "id", "course", "name", "description", "content",
            "link_to_video", "duration", "serial_number", "is_completed",
        ]

    def get_is_completed(self, obj: Lesson) -> bool:
        """
        Проверяет, отмечен ли урок пройденным текущим студентом.

        Args:
            obj: Объект урока.

        Returns:
            True, если id урока в context['completed_lessons'].
        """
        completed_lessons = self.context.get("completed_lessons", [])
        return obj.id in completed_lessons

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Валидирует уникальность serial_number и права на курс преподавателя.

        Args:
            data: Поля урока.

        Returns:
            Проверенные данные.
        """
        course = data.get("course") or (self.instance.course if self.instance else None)
        serial = data.get("serial_number") or (self.instance.serial_number if self.instance else None)

        if course is not None and serial is not None:
            if Lesson.objects.filter(course=course, serial_number=serial).exclude(
                id=self.instance.id if self.instance else None
            ).exists():
                raise serializers.ValidationError({
                    "serial_number": "Порядковый номер урока должен быть уникальным в рамках курса.",
                })

        request = self.context.get("request")
        if course is not None and request and request.user.is_authenticated and request.user.is_staff:
            if course.teacher_id != request.user.id:
                raise serializers.ValidationError({
                    "course": "Можно управлять уроками только своих курсов.",
                })
        return data


class AssignmentSerializer(serializers.ModelSerializer):
    """Сериализатор задания с флагами просрочки и отправки решения."""

    is_overdue = serializers.SerializerMethodField()
    has_submitted = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = [
            "id", "lesson", "name", "description", "max_score", "due_date",
            "is_overdue", "has_submitted",
        ]

    def get_is_overdue(self, obj: Assignment) -> bool:
        """
        Определяет, истёк ли срок сдачи задания.

        Args:
            obj: Объект задания.

        Returns:
            True, если due_date в прошлом.
        """
        return obj.due_date < timezone.now()

    def get_has_submitted(self, obj: Assignment) -> bool:
        """
        Проверяет, отправлял ли текущий студент решение по заданию.

        Args:
            obj: Объект задания.

        Returns:
            True, если id задания в context['submitted_assignments'].
        """
        submitted_assignments = self.context.get("submitted_assignments", [])
        return obj.id in submitted_assignments

    def validate_max_score(self, value: int) -> int:
        """
        Валидирует положительный максимальный балл.

        Args:
            value: Максимальный балл.

        Returns:
            Проверенное значение.
        """
        if value <= 0:
            raise serializers.ValidationError("Максимальный балл должен быть положительным числом.")
        return value

    def validate_due_date(self, value: datetime) -> datetime:
        """
        Валидирует, что срок сдачи в будущем.

        Args:
            value: Дата и время дедлайна.

        Returns:
            Проверенное значение.
        """
        if value <= timezone.now():
            raise serializers.ValidationError("Срок сдачи должен быть в будущем.")
        return value

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Проверяет, что задание создаётся только для курса текущего преподавателя.

        Args:
            data: Поля задания.

        Returns:
            Проверенные данные.
        """
        lesson = data.get("lesson") or (self.instance.lesson if self.instance else None)
        request = self.context.get("request")
        if lesson is not None and request and request.user.is_authenticated and request.user.is_staff:
            if lesson.course.teacher_id != request.user.id:
                raise serializers.ValidationError({
                    "lesson": "Можно управлять заданиями только своих курсов.",
                })
        return data


class EnrollmentSerializer(serializers.ModelSerializer):
    """Сериализатор записи студента на курс."""

    class Meta:
        model = Enrollment
        fields = ["id", "student", "course", "enrolled_at", "progress", "completed_at"]
        read_only_fields = ("student", "enrolled_at", "progress", "completed_at")

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Запрещает повторную запись студента на один курс.

        Args:
            data: Поля записи.

        Returns:
            Проверенные данные.
        """
        student = data.get("student")
        course = data.get("course")

        request = self.context.get("request")
        if not student and request and request.user.is_authenticated:
            student = request.user

        if student and course and Enrollment.objects.filter(student=student, course=course).exists():
            raise serializers.ValidationError("Вы уже записаны на этот курс.")
        return data


class SubmissionSerializer(serializers.ModelSerializer):
    """Сериализатор решения студента с правилами отправки и оценивания."""

    class Meta:
        model = Submission
        fields = [
            "id", "assignment", "student", "answer", "file", "score",
            "teacher_comment", "submitted_at", "status",
        ]
        read_only_fields = ("student", "submitted_at", "status")

    def validate_score(self, value: int | None) -> int | None:
        """
        Валидирует оценку в диапазоне 0..max_score задания.

        Args:
            value: Выставляемая оценка.

        Returns:
            Проверенная оценка или None.
        """
        if value is None:
            return value
        assignment = self.instance.assignment
        if value > assignment.max_score:
            raise serializers.ValidationError(
                f"Оценка не может превышать {assignment.max_score}."
            )
        if value < 0:
            raise serializers.ValidationError("Оценка не может быть отрицательной.")
        return value

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Валидирует отправку и изменение решения (запись на курс, уникальность, права).

        Args:
            data: Поля решения.

        Returns:
            Проверенные данные.
        """
        request = self.context.get("request")

        if self.instance is not None:
            if not (request and request.user.is_authenticated and request.user.is_staff):
                raise serializers.ValidationError("Только преподаватель может изменять решение.")
            course = self.instance.assignment.lesson.course
            if course.teacher_id != request.user.id:
                raise serializers.ValidationError(
                    "Только преподаватель курса может выставить оценку и изменить статус решения."
                )
            return data

        assignment = data.get("assignment")
        if assignment is None or not request or not request.user.is_authenticated:
            return data

        user = request.user

        answer = data.get("answer", "")
        file = data.get("file")
        if not (answer and str(answer).strip()) and not file:
            raise serializers.ValidationError({
                "answer": "Укажите текст решения и/или прикрепите файл.",
            })

        if Submission.objects.filter(student=user, assignment=assignment).exists():
            existing = Submission.objects.get(student=user, assignment=assignment)
            if existing.status == "checked":
                raise serializers.ValidationError({
                    "assignment": "Решение уже проверено, повторная отправка невозможна.",
                })
            raise serializers.ValidationError({
                "assignment": "Вы уже отправили решение по этому заданию.",
            })

        course = assignment.lesson.course
        if not Enrollment.objects.filter(student=user, course=course).exists():
            raise serializers.ValidationError({
                "assignment": "Вы не записаны на курс, поэтому не можете отправить решение.",
            })

        if not user.is_staff:
            student = data.get("student")
            if student is not None and student.id != user.id:
                raise serializers.ValidationError({
                    "student": "Нельзя отправить решение за другого студента.",
                })

        return data


class ProgressSerializer(serializers.ModelSerializer):
    """Сериализатор прогресса студента по уроку."""

    class Meta:
        model = Progress
        fields = ["id", "student", "lesson", "completed", "completed_at"]
