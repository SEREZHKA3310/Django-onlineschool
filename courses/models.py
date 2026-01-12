from django.db import models
from django.contrib.auth.models import AbstractUser
from simple_history.models import HistoricalRecords


class User(AbstractUser):
    ROLE_CHOICES = [
        ("teacher", "Teacher"),
        ("student", "Student"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="student")
    created_at = models.DateTimeField("Дата регистрации", auto_now_add=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    @property
    def is_teacher(self):
        return self.role == "teacher"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"


# Курс
class Course(models.Model):
    level_choices = [('beginner', 'Beginner'), ('intermediate', 'Intermediate'), ('advanced', 'Advanced')]
    category_choices = [('programming', 'Programming'), ('design', 'Design'), ('marketing', 'Marketing'), ('business', 'Business')]
    unit_of_time_choices = [('hours', 'Часы'), ('weeks', 'Недели'), ('months', 'Месяцы')]

    name = models.CharField("Название", max_length=50)
    description = models.TextField("Описание", max_length=250)
    price = models.PositiveIntegerField("Цена")
    unit_of_time = models.CharField("Единица измерения", max_length=10, choices=unit_of_time_choices)
    duration = models.PositiveIntegerField("Длительность")
    level = models.CharField("Уровень", max_length=20, choices=level_choices)
    category = models.CharField("Категория", max_length=20, choices=category_choices)
    image = models.ImageField(upload_to="images/")
    published = models.BooleanField("Опубликован")
    created_at = models.DateField("Дата создания", auto_now_add=True)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name="teaching_courses", verbose_name="Преподаватель")
    # Связь через Enrollment
    students = models.ManyToManyField(
        User,
        through='Enrollment',
        related_name="enrolled_courses",
        verbose_name="Студенты"
    )

    class Meta:
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"

    def __str__(self):
        return self.name

    history = HistoricalRecords()


# Урок
class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons", verbose_name="Курс")
    name = models.CharField("Название", max_length=50)
    description = models.TextField("Описание", max_length=250)
    content = models.TextField("Содержание")
    link_to_video = models.TextField("Ссылка на видео", blank=True, null=True)
    duration = models.DecimalField("Длительность (часы/минуты)", max_digits=5, decimal_places=1)
    serial_number = models.PositiveIntegerField("Порядковый номер")

    class Meta:
        verbose_name = "Урок"
        verbose_name_plural = "Уроки"
        ordering = ['course', 'serial_number']

    def __str__(self):
        return f"{self.course.name}: {self.serial_number}. {self.name}"

    history = HistoricalRecords()


# Запись на курс
class Enrollment(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Студент")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, verbose_name="Курс", related_name="enrollments")
    enrolled_at = models.DateTimeField("Дата записи", auto_now_add=True)
    progress = models.DecimalField("Прогресс (%)", max_digits=5, decimal_places=2, default=0)
    completed_at = models.DateTimeField("Дата завершения", null=True, blank=True)

    class Meta:
        verbose_name = "Запись на курс"
        verbose_name_plural = "Записи на курсы"
        unique_together = ('student', 'course')

    def __str__(self):
        return f"{self.student} записан на {self.course.name}"


# Задание
class Assignment(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, verbose_name="Урок", related_name='assignments')
    name = models.CharField("Название", max_length=50)
    description = models.TextField("Описание", max_length=250)
    max_score = models.PositiveIntegerField("Максимальный балл")
    due_date = models.DateTimeField("Срок сдачи")

    class Meta:
        verbose_name = "Задание"
        verbose_name_plural = "Задания"

    def __str__(self):
        return f"Задание: {self.name} ({self.lesson.course.name})"


# Решение задания
class Submission(models.Model):
    status_choices = [
        ('pending', 'На проверке'),
        ('checked', 'Проверено'),
        ('late', 'Просрочено')
    ]

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, verbose_name="Задание")
    student = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Студент")
    answer = models.TextField("Решение")
    file = models.FileField("Файл", upload_to="submissions/", null=True, blank=True)
    score = models.PositiveIntegerField("Оценка", null=True, blank=True, default=0)
    teacher_comment = models.TextField("Комментарий преподавателя", null=True, blank=True)
    submitted_at = models.DateTimeField("Дата отправки", auto_now_add=True)
    status = models.CharField("Статус", max_length=20, choices=status_choices, default='pending')

    class Meta:
        verbose_name = "Решение задания"
        verbose_name_plural = "Решения заданий"

    def __str__(self):
        return f"Решение {self.student} для {self.assignment.name}"


# Прогресс урока
class Progress(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Студент")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, verbose_name="Урок")
    completed = models.BooleanField("Завершён", default=False)
    completed_at = models.DateTimeField("Дата завершения", null=True, blank=True)

    class Meta:
        verbose_name = "Прогресс по уроку"
        verbose_name_plural = "Прогресс по урокам"
        unique_together = ('student', 'lesson')

    def __str__(self):
        return f"Прогресс {self.student} по уроку {self.lesson.serial_number}"
