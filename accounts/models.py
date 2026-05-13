from __future__ import annotations

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from common.models import UUIDTimestampModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        if not email:
            raise ValueError("The email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    avatar = models.CharField(max_length=512, blank=True, default="")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = ["name"]

    objects = UserManager()

    def __str__(self) -> str:
        return self.email


class UserPreference(UUIDTimestampModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="preferences")
    theme = models.CharField(max_length=20, default="dark")
    language = models.CharField(max_length=20, default="en")
    timezone = models.CharField(max_length=64, default="UTC")
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    slack_enabled = models.BooleanField(default=False)
    webhook_enabled = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"Preferences for {self.user.email}"
