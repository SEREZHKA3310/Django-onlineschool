"""Тесты API и основных сценариев онлайн-школы."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from courses.models import Assignment, Course, Enrollment, Lesson, Submission

User = get_user_model()


class RoleFeaturesTestCase(TestCase):
    """Интеграционные тесты ролей преподавателя и студента."""

    def setUp(self) -> None:
        """Создаёт пользователей, курс, урок, задание и API-клиент."""
        self.admin = User.objects.create_user(
            username="admin", password="pass", is_staff=True, role="teacher",
        )
        self.student = User.objects.create_user(
            username="student", password="pass", role="student",
        )
        self.client = APIClient()
        self.admin_token = Token.objects.create(user=self.admin)
        self.student_token = Token.objects.create(user=self.student)

        self.course = Course.objects.create(
            name="Python Basics",
            description="Intro course",
            price=0,
            unit_of_time="weeks",
            duration=4,
            level="beginner",
            category="programming",
            image="images/test.jpg",
            published=True,
            teacher=self.admin,
        )
        self.lesson = Lesson.objects.create(
            course=self.course,
            name="Lesson 1",
            description="First lesson",
            content="Content",
            duration=1.0,
            serial_number=1,
        )
        self.assignment = Assignment.objects.create(
            lesson=self.lesson,
            name="HW1",
            description="Homework",
            max_score=100,
            due_date=timezone.now() + timedelta(days=7),
        )

    def test_catalog_shows_only_published_for_student(self) -> None:
        """Студент видит только опубликованные курсы в каталоге."""
        Course.objects.create(
            name="Draft",
            description="Hidden",
            price=1000,
            unit_of_time="weeks",
            duration=2,
            level="beginner",
            category="programming",
            image="images/test.jpg",
            published=False,
            teacher=self.admin,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.student_token.key}")
        response = self.client.get("/api/courses/")
        names = [c["name"] for c in response.data["results"]]
        self.assertIn("Python Basics", names)
        self.assertNotIn("Draft", names)

    def test_admin_can_create_lesson(self) -> None:
        """Преподаватель (staff) может создать урок в своём курсе."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")
        response = self.client.post("/api/lessons/", {
            "course": self.course.id,
            "name": "Lesson 2",
            "description": "Second",
            "content": "More content",
            "duration": "1.5",
            "serial_number": 2,
        })
        self.assertEqual(response.status_code, 201)

    def test_student_cannot_create_lesson(self) -> None:
        """Студент не может создавать уроки."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.student_token.key}")
        response = self.client.post("/api/lessons/", {
            "course": self.course.id,
            "name": "Hack",
            "description": "x",
            "content": "x",
            "duration": "1.0",
            "serial_number": 99,
        })
        self.assertEqual(response.status_code, 403)

    def test_enroll_and_complete_lesson_updates_progress(self) -> None:
        """После complete прогресс записи на курс равен 100%."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.student_token.key}")
        self.client.post(f"/api/courses/{self.course.id}/enroll/")
        response = self.client.post(f"/api/lessons/{self.lesson.id}/complete/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["course_progress"], 100.0)

    def test_submission_duplicate_blocked(self) -> None:
        """Повторная отправка решения по тому же заданию запрещена."""
        Enrollment.objects.create(student=self.student, course=self.course)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.student_token.key}")
        payload = {"assignment": self.assignment.id, "answer": "My answer"}
        self.assertEqual(self.client.post("/api/submissions/", payload).status_code, 201)
        self.assertEqual(self.client.post("/api/submissions/", payload).status_code, 400)

    def test_free_course_price_validation(self) -> None:
        """Цена курса не может превышать 100 000 ₽."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")
        response = self.client.patch(
            f"/api/courses/{self.course.id}/",
            {"price": 150_000},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_can_grade_submission(self) -> None:
        """Преподаватель курса может выставить оценку через grade."""
        Enrollment.objects.create(student=self.student, course=self.course)
        submission = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            answer="Done",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")
        response = self.client.patch(
            f"/api/submissions/{submission.id}/grade/",
            {"score": 90, "teacher_comment": "Good"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "checked")

    def test_course_list_includes_annotations(self) -> None:
        """Список курсов содержит students_count, lessons_count, average_score."""
        Enrollment.objects.create(student=self.student, course=self.course)
        Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            answer="Done",
            score=90,
            status="checked",
        )
        response = self.client.get("/api/courses/")
        course_data = response.data["results"][0]
        self.assertEqual(course_data["students_count"], 1)
        self.assertEqual(course_data["lessons_count"], 1)
        self.assertEqual(course_data["average_score"], 90.0)

    def test_empty_submission_rejected(self) -> None:
        """Пустое решение без текста и файла отклоняется."""
        Enrollment.objects.create(student=self.student, course=self.course)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.student_token.key}")
        response = self.client.post("/api/submissions/", {
            "assignment": self.assignment.id,
            "answer": "",
        })
        self.assertEqual(response.status_code, 400)


class AuthAPITestCase(APITestCase):
    """Тесты аутентификации по токену DRF."""

    def setUp(self) -> None:
        """Создаёт тестового студента."""
        self.user = User.objects.create_user(username="testuser", password="secret", role="student")

    def test_obtain_auth_token(self) -> None:
        """POST /api/auth/login/ возвращает токен для валидных учётных данных."""
        response = self.client.post("/api/auth/login/", {
            "username": "testuser",
            "password": "secret",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.data)
        self.assertTrue(Token.objects.filter(user=self.user).exists())
