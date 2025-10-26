from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User,
    Admin,
    Staff,
    Profile,
    Flight_model,
    PriceIncrement,
    ThriveAdmin,
)


class UserAdmin(BaseUserAdmin):
    # Define the fieldsets for the user admin view
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {
         "fields": ("first_name", "last_name", "email", "phone")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
    )
    list_display = ("username", "email", "first_name", "last_name", "is_staff")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)


class ThriveAdminAdmin(admin.ModelAdmin):
    # Display related fields from the User model using 'admin.username' and 'admin.email'
    list_display = (
        "get_username",
        "get_email",
        "first_name",
        "last_name",
        "phone",
    )
    search_fields = (
        "admin__username",
        "first_name",
        "last_name",
        "phone",
    )
    list_filter = ("admin__username",)  # Filter by user related field

    # Define methods to display fields from related User model
    def get_username(self, obj):
        return obj.admin.username

    get_username.short_description = "Username"

    def get_email(self, obj):
        return obj.admin.email

    get_email.short_description = "Email"


class AdminAdmin(admin.ModelAdmin):
    # Display related fields from the User model using 'admin.username' and 'admin.email'
    list_display = (
        "get_username",
        "get_email",
        "first_name",
        "last_name",
        "phone",
    )
    search_fields = (
        "admin__username",
        "first_name",
        "last_name",
        "phone",
    )
    list_filter = ("admin__username",)  # Filter by user related field

    # Define methods to display fields from related User model
    def get_username(self, obj):
        return obj.admin.username

    get_username.short_description = "Username"

    def get_email(self, obj):
        return obj.admin.email

    get_email.short_description = "Email"


class StaffAdmin(admin.ModelAdmin):
    list_display = (
        "get_username",
        "get_email",
        "first_name",
        "last_name",
        "phone",
    )
    search_fields = (
        "staff__username",
        "first_name",
        "last_name",
        "phone",
    )

    # Define methods to display fields from related User model
    def get_username(self, obj):
        return obj.staff.username

    get_username.short_description = "Username"

    def get_email(self, obj):
        return obj.staff.email

    get_email.short_description = "Email"


class ProfileAdmin(admin.ModelAdmin):
    # Display related fields from the User model using 'user.username' and 'user.email'
    list_display = ("get_username", "profile_picture")
    search_fields = ("user__username",)  # Add a comma here to make it a tuple

    # Define methods to display fields from related User model
    def get_username(self, obj):
        return obj.user.username

    get_username.short_description = "Username"


class Flight_modelAdmin(admin.ModelAdmin):
    list_display = (
        "get_user_first_name",
        "get_user_last_name",
        "origin",
        "destination",
        "departure_date",
        "return_date",
        "passenger_count",
        "travel_class",
        "price",  # Add price to list_display
        "approved",  # Add approved status to list_display
    )
    search_fields = (
        "user__first_name",
        "user__last_name",
        "origin",
        "destination",
        "departure_date",
        "return_date",
        "travel_class",
        "user__username",
    )
    list_filter = (
        "departure_date",
        "return_date",
        "travel_class",
        "user",
        "approved",  # Add approved status to list_filter
    )
    raw_id_fields = ("user",)

    # Define method to get the first name from the related User model
    def get_user_first_name(self, obj):
        return obj.user.first_name

    get_user_first_name.short_description = 'First Name'

    # Define method to get the last name from the related User model
    def get_user_last_name(self, obj):
        return obj.user.last_name

    get_user_last_name.short_description = 'Last Name'



# Register the PriceIncrement model in the admin interface
class PriceIncrementAdmin(admin.ModelAdmin):
    list_display = ("increment_value",)  # Display the increment value
    search_fields = ("increment_value",)  # Allow searching by increment value


# Register models
admin.site.register(User, UserAdmin)
admin.site.register(Admin, AdminAdmin)
admin.site.register(Staff, StaffAdmin)
admin.site.register(Profile, ProfileAdmin)
admin.site.register(Flight_model, Flight_modelAdmin)
admin.site.register(PriceIncrement, PriceIncrementAdmin)
admin.site.register(ThriveAdmin, ThriveAdminAdmin)
