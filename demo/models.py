# models.py
from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser
import datetime

# Custom User model
class User(AbstractUser):
    username = models.CharField(max_length=200, null=True, unique=True)
    email = models.EmailField(unique=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)  
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']  
    
    
    # Thrive Admin
    
class ThriveAdmin(models.Model):
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="thrive_admin_profile")
    first_name = models.CharField(max_length=100, default='first_name')
    last_name = models.CharField(max_length=100, default='last_name')
    phone = models.CharField(max_length=15, blank=True, null=True)  # Added phone field
    approval_status = models.BooleanField(default=False)  # Added approval

    def __str__(self):
        return f'{self.admin.username} Thrive Profile'
    
    

# Admin model
class Admin(models.Model):
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="admin_profile")
    first_name = models.CharField(max_length=100, default='first_name')
    last_name = models.CharField(max_length=100, default='last_name')
    phone = models.CharField(max_length=15, blank=True, null=True)  # Added phone field
    approval_status = models.BooleanField(default=False)  # Added approval

    def __str__(self):
        return f'{self.admin.username} Admin Profile'
    


# Staff model
class Staff(models.Model):
    staff = models.ForeignKey(User, on_delete=models.CASCADE, related_name="staff_profile")
    first_name = models.CharField(max_length=100, default='first_name')
    last_name = models.CharField(max_length=100, default='last_name')
    phone = models.CharField(max_length=15, blank=True, null=True)  # Added phone field

    def __str__(self):
        return f'{self.staff.username} Staff Profile'

class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    profile_picture = models.ImageField(default="default.png",upload_to='profile_pictures/', blank=True, null=True)
    

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
    
    # New field for approval status
    approved = models.BooleanField(default=False)

    def __str__(self):
        return f"Flight from {self.origin} to {self.destination} on {self.departure_date}"
    
    


class PriceIncrement(models.Model):
    increment_value = models.IntegerField(default=0)
    

    def __str__(self):
        return f'Price Increment: {self.increment_value}'

