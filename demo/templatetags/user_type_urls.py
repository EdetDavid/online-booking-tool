from django import template
from django.urls import reverse
from demo.models import Staff, Admin, TravelAgency

register = template.Library()

@register.simple_tag
def get_profile_url(user):
    # Check if the user is associated with a Staff object
    if Staff.objects.filter(staff=user).exists():
        return reverse('profile')  # Assuming 'profile' is the Staff profile URL

    # Check if the user is associated with an Admin object
    elif Admin.objects.filter(admin=user).exists():
        return reverse('admin_profile')  # Assuming 'admin_profile' is the Admin profile URL

    # Check if the user is associated with a Travel Agency profile
    elif TravelAgency.objects.filter(admin=user).exists():
        return reverse('travel_agency_approval_view')

    # Default fallback if none of the above applies
    return reverse('profile')  # Default profile URL
