from typing import Any, ClassVar

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from apps.core.models import TimeStampedModel


class Role(models.TextChoices):
    CUSTOMER = "CUSTOMER", "Consumidor"
    MERCHANT_OWNER = "MERCHANT_OWNER", "Comerciante (proprietário)"
    MERCHANT_MANAGER = "MERCHANT_MANAGER", "Comerciante (gerente)"
    MERCHANT_OPERATOR = "MERCHANT_OPERATOR", "Comerciante (operador)"
    MODERATOR = "MODERATOR", "Moderador"
    SUPPORT = "SUPPORT", "Suporte"
    ADMIN = "ADMIN", "Administrador"
    SUPERADMIN = "SUPERADMIN", "Superadministrador"


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create(self, email: str, password: str | None, **extra: Any) -> "User":
        if not email:
            raise ValueError("email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("role", Role.CUSTOMER)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.update(role=Role.SUPERADMIN, is_staff=True, is_superuser=True)
        return self._create(email, password, **extra)


class User(TimeStampedModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=120, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    # Set when the account was deleted/anonymized (LGPD). The row stays so that
    # price history and audit references remain consistent without personal data.
    anonymized_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    def __str__(self) -> str:
        return self.email

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None


class ConsentPurpose(models.TextChoices):
    TERMS = "TERMS", "Termos de uso"
    PRIVACY_POLICY = "PRIVACY_POLICY", "Política de privacidade"
    LOCATION = "LOCATION", "Uso da localização"
    PHOTO_PROCESSING = "PHOTO_PROCESSING", "Processamento de fotografias"
    MARKETING_NOTIFICATIONS = "MARKETING_NOTIFICATIONS", "Notificações promocionais"


class Consent(TimeStampedModel):
    """Append-only history: each grant or revocation is a new row. Latest row wins."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consents"
    )
    purpose = models.CharField(max_length=40, choices=ConsentPurpose.choices)
    granted = models.BooleanField()
    policy_version = models.CharField(max_length=40)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "purpose", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.user_id} {self.purpose}={self.granted}"
