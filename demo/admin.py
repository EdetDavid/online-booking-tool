from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User,
    Organization,
    Admin,
    Staff,
    Profile,
    Flight_model,
    PriceIncrement,
    TravelAgency,
    LocalFlightFare,
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


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "join_code", "travel_agency", "active", "created_at")
    search_fields = ("name", "join_code", "travel_agency__admin__username", "travel_agency__admin__email")
    list_filter = ("active",)
    raw_id_fields = ("travel_agency",)


class TravelAgencyAdmin(admin.ModelAdmin):
    # Display related fields from the User model using 'admin.username' and 'admin.email'
    list_display = (
        "get_username",
        "get_email",
        "first_name",
        "last_name",
        "company_code",
        "approval_status",
        "phone",
    )
    search_fields = (
        "admin__username",
        "admin__email",
        "company_code",
        "first_name",
        "last_name",
        "phone",
    )
    list_filter = ("approval_status", "admin__username")

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
        "organization",
        "phone",
    )
    search_fields = (
        "admin__username",
        "organization__name",
        "first_name",
        "last_name",
        "phone",
    )
    list_filter = ("organization", "approval_status", "admin__username")
    raw_id_fields = ("organization",)

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
        "organization",
        "phone",
    )
    search_fields = (
        "staff__username",
        "organization__name",
        "first_name",
        "last_name",
        "phone",
    )
    list_filter = ("organization",)
    raw_id_fields = ("organization",)

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
        "organization",
        "travel_agency",
        "requested_by_staff",
        "assigned_admin",
        "approved_by_admin",
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
        "organization__name",
        "travel_agency__admin__username",
        "travel_agency__admin__email",
        "requested_by_staff__staff__username",
        "assigned_admin__admin__username",
        "approved_by_admin__admin__username",
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
        "organization",
        "travel_agency",
        "user",
        "approved",  # Add approved status to list_filter
    )
    raw_id_fields = ("user", "organization", "travel_agency", "requested_by_staff", "assigned_admin", "approved_by_admin")

    # Define method to get the first name from the related User model
    def get_user_first_name(self, obj):
        user = obj.requesting_user()
        return user.first_name if user else ""

    get_user_first_name.short_description = 'First Name'

    # Define method to get the last name from the related User model
    def get_user_last_name(self, obj):
        user = obj.requesting_user()
        return user.last_name if user else ""

    get_user_last_name.short_description = 'Last Name'



# Register the PriceIncrement model in the admin interface
class PriceIncrementAdmin(admin.ModelAdmin):
    list_display = ("increment_value",)  # Display the increment value
    search_fields = ("increment_value",)  # Allow searching by increment value


class LocalFlightFareAdmin(admin.ModelAdmin):
    list_display = (
        "origin",
        "destination",
        "airline_code",
        "cabin",
        "base_price_naira",
        "departure_time",
        "arrival_time",
        "stop_airport",
        "seats_available",
        "active",
    )
    list_filter = ("origin", "destination", "cabin", "airline_code", "active")
    search_fields = ("origin", "destination", "airline_code", "airline_name")


# Register models
admin.site.register(User, UserAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(Admin, AdminAdmin)
admin.site.register(Staff, StaffAdmin)
admin.site.register(Profile, ProfileAdmin)
admin.site.register(Flight_model, Flight_modelAdmin)
admin.site.register(PriceIncrement, PriceIncrementAdmin)
admin.site.register(TravelAgency, TravelAgencyAdmin)
admin.site.register(LocalFlightFare, LocalFlightFareAdmin)
