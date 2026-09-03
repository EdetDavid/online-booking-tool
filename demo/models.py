# models.py
from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from decimal import Decimal
import datetime

from .pricing import DEFAULT_EXCHANGE_RATE

# Custom User model
class User(AbstractUser):
    username = models.CharField(max_length=200, null=True, unique=True)
    email = models.EmailField(unique=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)  
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']  
    
    
class Organization(models.Model):
    name = models.CharField(max_length=200, unique=True)
    join_code = models.CharField(max_length=50, unique=True, null=True, blank=True)
    travel_agency = models.ForeignKey(
        "TravelAgency",
        on_delete=models.SET_NULL,
        related_name="organizations",
        null=True,
        blank=True,
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def normalize_join_code(cls, value):
        return "".join(str(value or "").split()).upper()

    @classmethod
    def unique_join_code(cls, name):
        base = cls.normalize_join_code(name)[:12] or "ORG"
        code = base
        suffix = 2
        while cls.objects.filter(join_code=code).exists():
            code = f"{base}{suffix}"
            suffix += 1
        return code

    @classmethod
    def get_or_create_by_name(cls, name):
        normalized = " ".join(str(name or "").split())
        organization = cls.objects.filter(name__iexact=normalized).first()
        if organization:
            return organization
        return cls.objects.create(
            name=normalized,
            join_code=cls.unique_join_code(normalized),
        )


class TravelAgency(models.Model):
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="travel_agency_profile")
    first_name = models.CharField(max_length=100, default='first_name')
    last_name = models.CharField(max_length=100, default='last_name')
    phone = models.CharField(max_length=15, blank=True, null=True)  # Added phone field
    company_code = models.CharField(max_length=50, unique=True, null=True, blank=True)
    approval_status = models.BooleanField(default=False)  # Added approval
    exchange_rate = models.DecimalField(
        "USD to NGN exchange rate",
        max_digits=12,
        decimal_places=4,
        default=DEFAULT_EXCHANGE_RATE,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )

    def __str__(self):
        return f'{self.admin.username} Travel Agency Profile'
    
    

# Admin model
class Admin(models.Model):
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="admin_profile")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="admins",
        null=True,
    )
    first_name = models.CharField(max_length=100, default='first_name')
    last_name = models.CharField(max_length=100, default='last_name')
    phone = models.CharField(max_length=15, blank=True, null=True)  # Added phone field
    approval_status = models.BooleanField(default=False)  # Added approval

    def __str__(self):
        return f'{self.admin.username} Admin Profile'
    


# Staff model
class Staff(models.Model):
    staff = models.ForeignKey(User, on_delete=models.CASCADE, related_name="staff_profile")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="staff_members",
        null=True,
    )
    first_name = models.CharField(max_length=100, default='first_name')
    last_name = models.CharField(max_length=100, default='last_name')
    phone = models.CharField(max_length=15, blank=True, null=True)  # Added phone field

    def __str__(self):
        return f'{self.staff.username} Staff Profile'

class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    profile_picture = models.ImageField(
        upload_to='profile_pictures/',
        blank=True,
        null=True,
    )
    

    def __str__(self):
        return f'{self.user.username} Profile'




class Flight_model(models.Model):
    # Existing fields
    origin = models.CharField(max_length=100)
    destination = models.CharField(max_length=100)
    departure_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    passenger_count = models.PositiveIntegerField()
    travel_class = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    
    # New field for user association
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='flights',
        null=True,
        blank=True
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name='flight_requests',
        null=True,
        blank=True
    )
    travel_agency = models.ForeignKey(
        TravelAgency,
        on_delete=models.SET_NULL,
        related_name='flight_requests',
        null=True,
        blank=True
    )
    requested_by_staff = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        related_name='flight_requests',
        null=True,
        blank=True
    )
    assigned_admin = models.ForeignKey(
        Admin,
        on_delete=models.SET_NULL,
        related_name='assigned_flight_requests',
        null=True,
        blank=True
    )
    approved_by_admin = models.ForeignKey(
        Admin,
        on_delete=models.SET_NULL,
        related_name='approved_flight_requests',
        null=True,
        blank=True
    )
    
    # New field for approval status
    approved = models.BooleanField(default=False)
    booking_payload = models.JSONField(null=True, blank=True)
    booking_completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Flight from {self.origin} to {self.destination} on {self.departure_date}"

    def requesting_user(self):
        if self.requested_by_staff_id:
            return self.requested_by_staff.staff
        return self.user

    def organization_admins(self):
        if self.assigned_admin_id:
            return Admin.objects.filter(id=self.assigned_admin_id)

        organization = self.organization
        if not organization and self.requested_by_staff_id:
            organization = self.requested_by_staff.organization

        if organization:
            return Admin.objects.filter(
                organization=organization,
                approval_status=True,
                admin__is_active=True,
                admin__email__isnull=False,
            ).exclude(admin__email="")

        return Admin.objects.none()

    @staticmethod
    def unique_emails(emails):
        seen = set()
        cleaned = []
        for email in emails:
            normalized = (email or "").strip()
            key = normalized.lower()
            if normalized and key not in seen:
                cleaned.append(normalized)
                seen.add(key)
        return cleaned

    def requester_emails(self):
        requester = self.requesting_user()
        return self.unique_emails([getattr(requester, "email", "")])

    def organization_admin_emails(self):
        return self.unique_emails(
            self.organization_admins().values_list("admin__email", flat=True)
        )

    def mapped_travel_agency(self):
        if self.travel_agency_id:
            return self.travel_agency
        if self.organization_id:
            return self.organization.travel_agency
        return None
    
    


class PriceIncrement(models.Model):
    increment_value = models.IntegerField(default=0)
    

    def __str__(self):
        return f'Price Increment: {self.increment_value}'


class LocalFlightFare(models.Model):
    CABIN_CHOICES = [
        ('ECONOMY', 'Economy'),
        ('PREMIUM_ECONOMY', 'Premium Economy'),
        ('BUSINESS', 'Business'),
        ('FIRST', 'First'),
    ]

    origin = models.CharField(max_length=3)
    destination = models.CharField(max_length=3)
    airline_code = models.CharField(max_length=3, default='B6')
    airline_name = models.CharField(max_length=100, default='JetBlue')
    cabin = models.CharField(max_length=20, choices=CABIN_CHOICES, default='ECONOMY')
    base_price_naira = models.DecimalField(max_digits=12, decimal_places=2)
    departure_time = models.TimeField()
    arrival_time = models.TimeField()
    return_departure_time = models.TimeField(null=True, blank=True)
    return_arrival_time = models.TimeField(null=True, blank=True)
    stop_airport = models.CharField(max_length=3, blank=True, default='')
    flight_duration = models.CharField(max_length=20, default='PT1H15M')
    return_duration = models.CharField(max_length=20, blank=True, default='')
    seats_available = models.PositiveIntegerField(default=9)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['origin', 'destination', 'base_price_naira']
        indexes = [
            models.Index(fields=['origin', 'destination', 'cabin', 'active'], name='demo_localf_origin_62574a_idx'),
        ]

    def __str__(self):
        return f'{self.origin}-{self.destination} {self.cabin} {self.airline_code} NGN {self.base_price_naira}'
