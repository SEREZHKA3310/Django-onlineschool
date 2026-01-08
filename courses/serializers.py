from rest_framework import serializers
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import (
    Course, Lesson, Assignment, Enrollment, Submission, Progress
)

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email",]

class CourseSerializer(serializers.ModelSerializer):
    teacher = UserSerializer(read_only=True)
    
    class Meta:
        model = Course
        fields = ["id", "name", "description", "price", "unit_of_time", "duration", "level", "category", "image", "published", "created_at", "teacher", "students",]
        read_only_fields = ("created_at", "teacher", "students")

    def validate_level(self, value):
        valid = ['beginner', 'intermediate', 'advanced']
        if value not in valid:
            raise serializers.ValidationError("Уровень должен быть beginner/intermediate/advanced.")
        return value

    def validate_category(self, value):
        valid = ['programming', 'design', 'marketing', 'business']
        if value not in valid:
            raise serializers.ValidationError("Категория должна быть одной из: programming, design, marketing, business.")
        return value

    def validate(self, data):
        if data.get("price", 1) <= 0:
            raise serializers.ValidationError({"price": "Цена должна быть положительным числом."})
        if data.get("duration", 1) <= 0:
            raise serializers.ValidationError({"duration": "Длительность должна быть положительной."})
        return data

    def create(self, validated_data):
        user = self.context["request"].user
        if not user.is_teacher:
            raise serializers.ValidationError("Создавать курсы могут только преподаватели.")
        validated_data["teacher"] = user
        return super().create(validated_data)

class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ["id", "course", "name", "description", "content", "link_to_video", "duration", "serial_number",]

    def validate(self, data):
        course = data.get("course") or self.instance.course
        serial = data.get("serial_number") or self.instance.serial_number

        if Lesson.objects.filter(
                course=course,
                serial_number=serial
        ).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError({
                "serial_number": "Порядковый номер урока должен быть уникальным в рамках курса."
            })
        return data

class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assignment
        fields = ["id", "lesson", "name", "description", "max_score", "due_date",]

    def validate_max_score(self, value):
        if value <= 0:
            raise serializers.ValidationError("Максимальный балл должен быть положительным числом.")
        return value

class EnrollmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Enrollment
        fields = ["id", "student", "course", "enrolled_at", "progress", "completed_at",]
        read_only_fields = ("student", "enrolled_at", "progress", "completed_at")

class SubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Submission
        fields = ["id", "assignment", "student", "answer", "file", "score", "teacher_comment", "submitted_at", "status",]
        read_only_fields = ("student", "submitted_at", "status")

    def validate_score(self, value):
        assignment = self.instance.assignment
        max_score = assignment.max_score
        
        if value > max_score:
            raise serializers.ValidationError(f"Оценка не может превышать {max_score}.")
        if value < 0:
            raise serializers.ValidationError("Оценка не может быть отрицательной.")
        
        return value

    def validate(self, data):
        if self.instance is not None:
            return data
    
        request = self.context["request"]
        student = request.user
        assignment = data.get("assignment")

        if assignment is None:
            return data

        course = assignment.lesson.course

        if not Enrollment.objects.filter(student=student, course=course).exists():
            raise serializers.ValidationError({
                "assignment": "Вы не записаны на курс, поэтому не можете отправить решение."
            })
        return data

class ProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Progress
        fields = ["id", "student", "lesson", "completed", "completed_at",]