from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    # Preparer / firm identity shown on calculation reports (set in Settings).
    firm_name = models.CharField(max_length=150, blank=True)
    license_number = models.CharField(max_length=60, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    firm_address = models.CharField(max_length=255, blank=True)
    logo = models.ImageField(upload_to="firm_logos/", blank=True, null=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    def get_short_name(self):
        return self.first_name

    def preparer_name(self):
        """The person's name for a report byline, falling back to email."""
        return self.get_full_name() or self.email

    def has_report_identity(self):
        return bool(self.firm_name or self.get_full_name() or self.license_number)

    def logo_path(self):
        """Local filesystem path to the firm logo, or None if unset/remote."""
        if not self.logo:
            return None
        try:
            return self.logo.path
        except (NotImplementedError, ValueError):
            return None

    def __str__(self):
        return self.email
