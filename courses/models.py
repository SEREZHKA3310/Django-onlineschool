from __future__ import annotations

from datetime import datetime

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from simple_history.models import HistoricalRecords


class User(AbstractUser):
    """Пользователь платформы: преподаватель или студент."""

    ROLE_CHOICES = [("teacher", "Teacher"), ("student", "Student")]

    role = models.CharField("Роль", max_length=20, choices=ROLE_CHOICES, default="student")
    created_at = models.DateTimeField("Дата регистрации", auto_now_add=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    @property
    def is_teacher(self) -> bool:
        """Возвращает True, если роль пользователя — преподаватель."""
        return self.role == "teacher"

    def __str__(self) -> str:
        """Строковое представление пользователя."""
        return f"{self.first_name} {self.last_name} ({self.email})"


class Course(models.Model):
    """Учебный курс с метаданными, ценой и преподавателем."""

    level_choices = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]
    category_choices = [
        ("programming", "Programming"),
        ("design", "Design"),
        ("marketing", "Marketing"),
        ("business", "Business"),
    ]
    unit_of_time_choices = [("hours", "Часы"), ("weeks", "Недели"), ("months", "Месяцы")]

    name = models.CharField("Название", max_length=50)
    description = models.TextField("Описание", max_length=250)
    price = models.PositiveIntegerField("Цена")
    unit_of_time = models.CharField("Единица измерения", max_length=10, choices=unit_of_time_choices)
    duration = models.PositiveIntegerField("Длительность")
    level = models.CharField("Уровень", max_length=20, choices=level_choices)
    category = models.CharField("Категория", max_length=20, choices=category_choices)
    image = models.ImageField("Изображение", upload_to="images/")
    published = models.BooleanField("Опубликован")
    created_at = models.DateField("Дата создания", auto_now_add=True)
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="teaching_courses",
        verbose_name="Преподаватель",
    )
    students = models.ManyToManyField(
        User,
        through="Enrollment",
        related_name="enrolled_courses",
        verbose_name="Студенты",
    )

    class Meta:
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"

    def __str__(self) -> str:
        """Название курса."""
        return self.name

    history = HistoricalRecords()


class Lesson(models.Model):
    """Урок внутри курса с контентом и порядковым номером."""

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="lessons", verbose_name="Курс"
    )
    name = models.CharField("Название", max_length=50)
    description = models.TextField("Описание", max_length=250)
    content = models.TextField("Содержание")
    link_to_video = models.TextField("Ссылка на видео", blank=True, null=True)
    duration = models.DecimalField("Длительность (часы/минуты)", max_digits=5, decimal_places=1)
    serial_number = models.PositiveIntegerField("Порядковый номер")

    class Meta:
        verbose_name = "Урок"
        verbose_name_plural = "Уроки"
        ordering = ["course", "serial_number"]

    def __str__(self) -> str:
        """Краткое описание урока в контексте курса."""
        return f"{self.course.name}: {self.serial_number}. {self.name}"

    history = HistoricalRecords()


class Enrollment(models.Model):
    """Запись студента на курс с отслеживанием прогресса."""

    student = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Студент")
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="enrollments", verbose_name="Курс"
    )
    enrolled_at = models.DateTimeField("Дата записи", auto_now_add=True)
    progress = models.DecimalField("Прогресс (%)", max_digits=5, decimal_places=2, default=0)
    completed_at = models.DateTimeField("Дата завершения", null=True, blank=True)

    class Meta:
        verbose_name = "Запись на курс"
        verbose_name_plural = "Записи на курсы"
        unique_together = ("student", "course")

    def __str__(self) -> str:
        """Текст записи студента на курс."""
        return f"{self.student} записан на {self.course.name}"

    @classmethod
    def recalculate_progress(cls, student: User, course: Course) -> None:
        """
        Пересчитывает процент прогресса записи студента на курс.

        Args:
            student: Студент, для которого обновляется прогресс.
            course: Курс, по которому считается завершение уроков.
        """
        lessons_count = course.lessons.count()
        enrollment = cls.objects.filter(student=student, course=course).first()
        if not enrollment:
            return

        if lessons_count == 0:
            enrollment.progress = 0
            enrollment.save(update_fields=["progress"])
            return

        completed_count = Progress.objects.filter(
            student=student,
            lesson__course=course,
            completed=True,
        ).count()
        percent = round(completed_count / lessons_count * 100, 2)
        enrollment.progress = percent
        if percent >= 100 and not enrollment.completed_at:
            enrollment.completed_at = timezone.now()
        enrollment.save(update_fields=["progress", "completed_at"])


class Assignment(models.Model):
    """Задание к уроку с максимальным баллом и сроком сдачи."""

    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name="assignments", verbose_name="Урок"
    )
    name = models.CharField("Название", max_length=50)
    description = models.TextField("Описание", max_length=250)
    max_score = models.PositiveIntegerField("Максимальный балл")
    due_date = models.DateTimeField("Срок сдачи")

    class Meta:
        verbose_name = "Задание"
        verbose_name_plural = "Задания"

    def __str__(self) -> str:
        """Название задания и курс."""
        return f"Задание: {self.name} ({self.lesson.course.name})"

    def resolve_submission_status(self, submitted_at: datetime | None = None) -> str:
        """
        Определяет статус решения при отправке: pending или late.

        Args:
            submitted_at: Момент отправки; по умолчанию — текущее время.

        Returns:
            Строка статуса: ``late`` или ``pending``.
        """
        submitted_at = submitted_at or timezone.now()
        if submitted_at > self.due_date:
            return "late"
        return "pending"


class Submission(models.Model):
    """Решение студента по заданию с оценкой и статусом проверки."""

    status_choices = [
        ("pending", "На проверке"),
        ("checked", "Проверено"),
        ("late", "Просрочено"),
    ]

    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="submissions", verbose_name="Задание"
    )
    student = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Студент")
    answer = models.TextField("Решение")
    file = models.FileField("Файл", upload_to="submissions/", null=True, blank=True)
    score = models.PositiveIntegerField("Оценка", null=True, blank=True, default=0)
    teacher_comment = models.TextField("Комментарий преподавателя", null=True, blank=True)
    submitted_at = models.DateTimeField("Дата отправки", auto_now_add=True)
    status = models.CharField("Статус", max_length=20, choices=status_choices, default="pending")

    class Meta:
        verbose_name = "Решение задания"
        verbose_name_plural = "Решения заданий"
        unique_together = ("student", "assignment")

    def __str__(self) -> str:
        """Краткое описание решения."""
        return f"Решение {self.student} для {self.assignment.name}"


class Progress(models.Model):
    """Прогресс студента по отдельному уроку."""

    student = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Студент")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, verbose_name="Урок")
    completed = models.BooleanField("Завершён", default=False)
    completed_at = models.DateTimeField("Дата завершения", null=True, blank=True)

    class Meta:
        verbose_name = "Прогресс по уроку"
        verbose_name_plural = "Прогресс по урокам"
        unique_together = ("student", "lesson")

    def __str__(self) -> str:
        """Статус прохождения урока студентом."""
        return f"Прогресс {self.student} по уроку {self.lesson.serial_number}"
