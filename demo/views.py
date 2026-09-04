from django.utils.html import strip_tags
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from django.template.loader import render_to_string
import json
import ast
import urllib.parse
import csv
import xlwt
import logging
import requests
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
from amadeus import Client, ResponseError, Location
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.cache import never_cache
from .flight import Flight, flight_price_naira, flight_route_details
from .duffel import DuffelAPIError, airport_suggestions, search_flights as duffel_flight_search
from .booking import Booking
from .cart import (
    add_flight as add_flight_to_cart,
    add_hotel as add_hotel_to_cart,
    cart_count,
    cart_item_is_submitted,
    cart_items,
    cart_total_naira,
    clear_cart,
    flight_cart_state_counts,
    get_cart_item,
    has_removable_cart_items,
    remove_item as remove_cart_item,
    visible_cart_items,
)
from .hotel import Hotel, format_price_naira
from .room import Room
from .local_flights import (
    LOCAL_FARE_SOURCES,
    local_airport_search,
    local_booking_confirmation,
    local_flight_search,
    local_multi_city_search,
    normalize_cabin,
    normalize_iata,
)
from .local_hotels import (
    LOCAL_HOTEL_RESULTS_TARGET,
    hotel_city_label,
    is_local_hotel_id,
    is_local_hotel_offer_id,
    local_hotel_booking_confirmation,
    local_hotel_city_search,
    local_hotel_offer,
    local_hotel_search,
    local_room_search,
    normalize_city_code,
)
from .models import Admin, Staff, Profile, Flight_model, PriceIncrement, Organization, TravelAgency
from .pricing import exchange_rate_for_agency, exchange_rate_for_user
from .role_email import (
    role_recipients,
    send_html_email,
)
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from .forms import (
    AdminUserCreationForm,
    ExchangeRateForm,
    StaffUserCreationForm,
    ProfileForm,
    StandardAuthenticationForm,
    TravelAgencyAuthenticationForm,
    TravelAgencyOrganizationForm,
    TravelAgencyUserCreationForm,
    normalize_company_code,
)
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
logger = logging.getLogger(__name__)


amadeus = Client(
    client_id=settings.AMADEUS_CLIENT_ID or None,
    client_secret=settings.AMADEUS_CLIENT_SECRET or None,
    hostname=settings.AMADEUS_HOSTNAME,
)


def csrf_failure(request, reason=""):
    messages.error(
        request,
        "Your session expired. Please refresh the page and try again.",
    )
    referer = request.META.get('HTTP_REFERER')
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(referer)
    return redirect(reverse('login'))


def staff_profile_for_user(user):
    if not user.is_authenticated:
        return None
    return Staff.objects.select_related('organization').filter(staff=user).first()


def admin_profile_for_user(user):
    if not user.is_authenticated:
        return None
    return Admin.objects.select_related('organization').filter(
        admin=user,
        approval_status=True,
    ).first()


def travel_agency_profile_for_user(user):
    if not user.is_authenticated:
        return None
    return TravelAgency.objects.filter(admin=user, approval_status=True).first()


def redirect_for_user(user):
    if not user.is_authenticated:
        return 'home'
    if TravelAgency.objects.filter(admin=user, approval_status=True).exists():
        return 'travel_agency_organizations'
    if Admin.objects.filter(admin=user, approval_status=True).exists():
        return 'admin_profile'
    if Staff.objects.filter(staff=user).exists():
        return 'profile'
    return 'home'


def role_required(profile_getter, login_url, role_name):
    def decorator(view_func):
        @wraps(view_func)
        @login_required(login_url=login_url)
        def wrapper(request, *args, **kwargs):
            if profile_getter(request.user):
                return view_func(request, *args, **kwargs)
            messages.error(request, f'You do not have {role_name} access.')
            return redirect(redirect_for_user(request.user))
        return wrapper
    return decorator


staff_required = role_required(staff_profile_for_user, 'login', 'staff')
admin_required = role_required(admin_profile_for_user, 'admin_login', 'admin')
travel_agency_required = role_required(
    travel_agency_profile_for_user,
    'travel_agency_login',
    'travel agency',
)


def first_organization_admin(organization):
    if not organization:
        return None
    return Admin.objects.filter(
        organization=organization,
        approval_status=True,
        admin__is_active=True,
    ).first()


# ==========   ADMIN ============== >
# Admin Registration View
def admin_register(request):
    if request.method == 'POST':
        form = AdminUserCreationForm(request.POST)
        if form.is_valid():
            # Save the user but don't commit yet
            user = form.save(commit=False)
            user.is_active = True  # Allow the user to login, but without admin privileges
            user.save()  # Now save the user

            # Create a Profile for the user
            Profile.objects.create(user=user)
            organization = form.cleaned_data.get('organization')
            if not organization:
                organization = Organization.get_or_create_by_name(
                    form.cleaned_data['organization_name']
                )

            # Create the Admin profile with approval_status = False (unapproved)
            Admin.objects.create(
                admin=user,
                organization=organization,
                first_name=user.first_name,
                last_name=user.last_name,
                phone=user.phone,  # Assuming phone is captured in the form
                approval_status=False  # New admin is unapproved initially
            )

            # Log the user in after registration
            auth_login(request, user)

            # Notify the user that they are awaiting approval
            messages.success(
                request, 'Admin registration successful. Your account is awaiting approval from an existing admin.')

            # Redirect to a "waiting for approval" page instead of admin dashboard
            # You need to create this page
            return redirect('admin_login')
        else:
            messages.error(
                request, 'There was an error in the form. Please correct the errors.')
    else:
        form = AdminUserCreationForm()

    return render(request, 'demo/admin/admin_register.html', {'form': form})


@never_cache
def admin_login(request):
    if request.method == 'POST':
        form = StandardAuthenticationForm(data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)

            if user is not None:
                try:
                    # Check if the user has an admin profile
                    admin_profile = Admin.objects.get(admin=user)

                    if not admin_profile.approval_status:
                        messages.error(
                            request, 'Your account is awaiting approval from an existing admin.')
                        return render(request, 'demo/admin/admin_login.html', {'form': form})

                    # If approved, log in the admin
                    auth_login(request, user)
                    # messages.success(request, 'Admin login successful.')
                    return redirect('admin_profile')

                except Admin.DoesNotExist:
                    messages.error(request, 'You do not have admin access.')
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = StandardAuthenticationForm()

    return render(request, 'demo/admin/admin_login.html', {'form': form})


@admin_required
def admin_approval_view(request):
    current_admin = get_object_or_404(
        Admin, admin=request.user, approval_status=True)

    # Fetch all pending admins where approval_status is False
    pending_admins = Admin.objects.select_related(
        'admin',
        'organization',
    ).filter(approval_status=False).exclude(id=current_admin.id)

    if request.method == 'POST':
        admin_id = request.POST.get('admin_id')
        action = request.POST.get('action')

        # Fetch the admin by ID within the visible organization scope
        admin = get_object_or_404(pending_admins, id=admin_id)

        if action == 'approve':
            admin.approval_status = True  # Approve the admin
            admin.save()
            if (
                current_admin.organization_id
                and admin.organization_id
                and admin.organization_id != current_admin.organization_id
            ):
                messages.info(
                    request,
                    f'{admin.admin.username} belongs to {admin.organization.name}; you approved them outside your own organization.'
                )
            messages.success(
                request, f'{admin.admin.username} has been approved as an admin.')
        elif action == 'disapprove':
            # Disapprove the admin (or keep pending)
            admin.approval_status = False
            admin.save()
            messages.error(
                request, f'{admin.admin.username} has been disapproved.')

        return redirect('admin_approval_view')

    return render(request, 'demo/admin/admin_approval.html', {'pending_admins': pending_admins})


@admin_required
def admin_dashboard(request):
    return render(request, 'demo/admin/base.html')


def coming_soon(request):
    """Render a simple coming soon page for unfinished nav links."""
    return render(request, 'demo/coming_soon.html')


@admin_required
def approve_flight(request):
    admin_profile = admin_profile_for_user(request.user)

    pending_flights = Flight_model.objects.filter(approved=False)
    if admin_profile.organization_id:
        pending_flights = pending_flights.filter(
            organization=admin_profile.organization)

    if request.method == 'POST':
        # Get selected flights
        flight_ids = request.POST.getlist('flight_ids')

        if flight_ids:
            flights = pending_flights.filter(id__in=flight_ids)

            for flight in flights:
                flight.approved = True
                flight.approved_by_admin = admin_profile
                update_fields = ['approved', 'approved_by_admin']
                if not flight.assigned_admin_id:
                    flight.assigned_admin = admin_profile
                    update_fields.append('assigned_admin')
                flight.save(update_fields=update_fields)
                messages.success(
                    request, f'Flight {flight.origin} to {flight.destination} on {flight.departure_date} has been approved.')

                send_flight_approval_email(flight)

            return redirect('approve_flight')

    return render(request, 'demo/admin/approve_flight.html', {'pending_flights': pending_flights})


@admin_required
def admin_profile_view(request):
    # Ensure the user is authenticated before accessing the profile page
    profile = request.user.profile

    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            # Redirect to profile page after updating
            return redirect('admin_profile')
    else:
        form = ProfileForm(instance=profile)

    # Pass the form and user profile details to the template for rendering
    return render(request, 'demo/admin/profile.html', {
        'form': form,
        'user': request.user,  # Ensure user details are available in the template
    })


@admin_required
def admin_update_profile_picture(request):
    if request.method == 'POST':
        form = ProfileForm(
            request.POST,
            request.FILES,
            instance=request.user.profile,
        )
        if 'profile_picture' not in request.FILES:
            messages.error(request, 'Select a profile picture to upload.')
        elif form.is_valid():
            form.save()
            messages.success(request, 'Profile picture updated successfully.')
            return redirect('admin_profile')
        else:
            error = form.errors.get('profile_picture')
            messages.error(
                request,
                error[0] if error else 'No valid profile picture was selected.',
            )

    return redirect('admin_profile')


@admin_required
def staff_list(request):
    profile = request.user.profile
    form = ProfileForm(instance=profile)
    admin_profile = admin_profile_for_user(request.user)
    staffs = Staff.objects.all()
    if admin_profile and admin_profile.organization_id:
        staffs = staffs.filter(organization=admin_profile.organization)
    return render(request, 'demo/admin/staff_list.html', {'staffs': staffs, 'form': form})


# Admin Report
@admin_required
def report(request):
    admin_profile = admin_profile_for_user(request.user)
    flights = Flight_model.objects.all()
    staff_members = Staff.objects.all()
    admins = Admin.objects.all()
    if admin_profile and admin_profile.organization_id:
        flights = flights.filter(organization=admin_profile.organization)
        staff_members = staff_members.filter(
            organization=admin_profile.organization)
        admins = admins.filter(organization=admin_profile.organization)

    # Handle Export to CSV, Excel, or PDF
    if 'export' in request.GET:
        file_format = request.GET.get('export')
        if file_format == 'csv':
            return export_combined_to_csv(flights, staff_members, admins)
        elif file_format == 'excel':
            return export_combined_to_excel(flights, staff_members, admins)
        elif file_format == 'pdf':
            return export_combined_to_pdf(request, flights, staff_members, admins)

    return render(request, 'demo/admin/report.html', {
        'flights': flights,
        'staff_members': staff_members,
        'admins': admins
    })

# Export to CSV


def export_combined_to_csv(flights, staff_members, admins):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="report.csv"'

    writer = csv.writer(response)
    writer.writerow(['Flight Report'])
    writer.writerow(['First Name', 'Last Name', 'Organization', 'Agent', 'Origin', 'Destination',
                    'Travel Class', 'Departure Date', 'Return Date', 'Approved'])
    for flight in flights:
        requester = flight.requesting_user()
        travel_agency = flight.mapped_travel_agency()
        writer.writerow([
            requester.first_name if requester else '',
            requester.last_name if requester else '',
            flight.organization.name if flight.organization else '',
            str(travel_agency) if travel_agency else '',
            flight.origin,
            flight.destination,
            flight.travel_class,
            flight.departure_date,
            flight.return_date,
            'Approved' if flight.approved else 'Pending approval'
        ])

    writer.writerow([])
    writer.writerow(['Staff Report'])
    writer.writerow(['First Name', 'Last Name', 'Email', 'Phone'])
    for staff in staff_members:
        writer.writerow([
            staff.first_name,
            staff.last_name,
            staff.staff.email,
            staff.phone
        ])

    writer.writerow([])
    writer.writerow(['Admin Report'])
    writer.writerow(['First Name', 'Last Name', 'Email',
                    'Phone', 'Approval Status'])
    for admin in admins:
        writer.writerow([
            admin.first_name,
            admin.last_name,
            admin.admin.email,
            admin.phone,
            'Approved' if admin.approval_status else 'Not Approved'
        ])

    return response

# Export to Excel


def export_combined_to_excel(flights, staff_members, admins):
    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = 'attachment; filename="report.xlsx"'

    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('Report')

    row = 0

    # Flight Report
    ws.write(row, 0, 'Flight Report')
    row += 1
    columns = ['First Name', 'Last Name', 'Organization', 'Agent',
               'Origin', 'Destination', 'Travel Class', 'Departure Date', 'Return Date', 'Approved']
    for col_num, column in enumerate(columns):
        ws.write(row, col_num, column)
    row += 1
    for flight in flights:
        requester = flight.requesting_user()
        travel_agency = flight.mapped_travel_agency()
        ws.write(row, 0, requester.first_name if requester else '')
        ws.write(row, 1, requester.last_name if requester else '')
        ws.write(row, 2, flight.organization.name if flight.organization else '')
        ws.write(row, 3, str(travel_agency) if travel_agency else '')
        ws.write(row, 4, flight.origin)
        ws.write(row, 5, flight.destination)
        ws.write(row, 6, flight.travel_class)
        ws.write(row, 7, flight.departure_date.strftime('%Y-%m-%d'))
        ws.write(row, 8, flight.return_date.strftime(
            '%Y-%m-%d') if flight.return_date else '')
        ws.write(row, 9, 'Approved' if flight.approved else 'Pending approval')
        row += 1

    ws.write(row, 0, 'Staff Report')
    row += 1
    columns = ['First Name', 'Last Name', 'Email', 'Phone']
    for col_num, column in enumerate(columns):
        ws.write(row, col_num, column)
    row += 1
    for staff in staff_members:
        ws.write(row, 0, staff.first_name)
        ws.write(row, 1, staff.last_name)
        ws.write(row, 2, staff.staff.email)
        ws.write(row, 3, staff.phone)
        row += 1

    ws.write(row, 0, 'Admin Report')
    row += 1
    columns = ['First Name', 'Last Name', 'Email', 'Phone', 'Approval Status']
    for col_num, column in enumerate(columns):
        ws.write(row, col_num, column)
    row += 1
    for admin in admins:
        ws.write(row, 0, admin.first_name)
        ws.write(row, 1, admin.last_name)
        ws.write(row, 2, admin.admin.email)
        ws.write(row, 3, admin.phone)
        ws.write(row, 4, 'Approved' if admin.approval_status else 'Not Approved')
        row += 1

    wb.save(response)
    return response

# Export to PDF (WeasyPrint)


def export_combined_to_pdf(request, flights, staff_members, admins):
    # Generate HTML from template
    html_string = render_to_string('demo/admin/report.html', {
        'flights': flights,
        'staff_members': staff_members,
        'admins': admins
    })

    # Create a PDF response using WeasyPrint
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="report.pdf"'

    # Import WeasyPrint at runtime so missing native dependencies don't break module import
    try:
        from weasyprint import HTML
        # Generate the PDF
        HTML(string=html_string).write_pdf(response)
        return response
    except (ImportError, OSError) as e:
        # Log error and provide a useful fallback message. On Windows WeasyPrint
        # requires native libraries (gobject/pango); failing import should not
        # crash the whole application.
        logger.error(f"WeasyPrint unavailable or runtime error: {e}")
        messages.error(
            request, "PDF generation requires WeasyPrint native dependencies (gobject/pango). See README for setup or install the required runtime.")
        # Fallback: return rendered HTML so the user still gets the report content
        return HttpResponse(html_string, content_type='text/html')


# =================== STAFF  =============>
def staff_register(request):
    if request.method == 'POST':
        form = StaffUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()  # This will now handle creating the Staff profile with phone
            # Get the phone number from the form
            # phone = form.cleaned_data.get('phone')
            # Create a profile for the new user and save the phone number
            Profile.objects.create(user=user)
            auth_login(request, user)  # Log the user in after registration
            messages.success(request, 'Staff registration successful.')
            # Redirect to home page after successful registration
            return redirect('profile')
        else:
            messages.error(request, 'There was an error in the form.')
    else:
        form = StaffUserCreationForm()
    return render(request, 'demo/auth/register.html', {'form': form})


@never_cache
def staff_login(request):
    if request.method == 'POST':
        form = StandardAuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            # Check if the user has a corresponding Staff profile
            try:
                staff = Staff.objects.get(staff=user)
                auth_login(request, user)
                # messages.success(request, 'Staff login successful.')
                # Redirect to staff dashboard
                next_url = request.POST.get('next')
                if next_url and url_has_allowed_host_and_scheme(
                    next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    return redirect(next_url)
                return redirect('profile')
            except Staff.DoesNotExist:
                messages.error(
                    request, 'Invalid credentials. You are not a staff member.')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = StandardAuthenticationForm()

    return render(request, 'demo/auth/login.html', {'form': form})


@staff_required
def pending_flights(request):
    # Get the authenticated user
    user = request.user
    staff_profile = staff_profile_for_user(user)

    # Filter flights where `approved` is False and `user` is the authenticated user
    pending_flights = Flight_model.objects.filter(approved=False)
    if staff_profile:
        pending_flights = pending_flights.filter(
            requested_by_staff=staff_profile)
    else:
        pending_flights = pending_flights.filter(user=user)
    pending_flights = pending_flights.order_by('-departure_date')
    return render(request, 'demo/staff/pending_flights.html', {'pending_flights': pending_flights})


@staff_required
def approved_flights(request):
    # Get the authenticated user
    user = request.user
    staff_profile = staff_profile_for_user(user)

    # Filter flights where `approved` is True and `user` is the authenticated user
    approved_flights = Flight_model.objects.filter(approved=True)
    if staff_profile:
        approved_flights = approved_flights.filter(
            requested_by_staff=staff_profile)
    else:
        approved_flights = approved_flights.filter(user=user)
    approved_flights = approved_flights.order_by('-departure_date')

    return render(request, 'demo/staff/approved_flights.html', {'approved_flights': approved_flights})


# =========     PROFILE ===================>

@staff_required
def profile_view(request):
    # Ensure the user is authenticated before accessing the profile page
    profile = request.user.profile

    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            # Redirect to profile page after updating
            return redirect('profile')
    else:
        form = ProfileForm(instance=profile)

    # Pass the form and user profile details to the template for rendering
    return render(request, 'demo/staff/profile.html', {
        'form': form,
        'user': request.user,  # Ensure user details are available in the template
    })


@staff_required
def update_profile_picture(request):
    if request.method == 'POST':
        form = ProfileForm(
            request.POST,
            request.FILES,
            instance=request.user.profile,
        )
        if 'profile_picture' not in request.FILES:
            messages.error(request, 'Select a profile picture to upload.')
        elif form.is_valid():
            form.save()
            messages.success(request, 'Profile picture updated successfully.')
            return redirect('profile')
        else:
            error = form.errors.get('profile_picture')
            messages.error(
                request,
                error[0] if error else 'No valid profile picture was selected.',
            )

    return redirect('profile')


# end profile

# Logout View
@login_required
def logout_view(request):
    auth_logout(request)
    return redirect('home')  # Redirect to login after logout


# ======= FLIGHT VIEWS =======================>


# Price Markup

@travel_agency_required
def update_price_increment(request):
    # Get the current increment value or create one if it doesn't exist
    increment, created = PriceIncrement.objects.get_or_create(
        id=1)  # Assuming you only need one instance

    if request.method == 'POST':
        # Get the updated increment value from the form
        increment_value = request.POST.get('increment_value')
        increment.increment_value = float(increment_value)
        increment.save()
        # Redirect after saving to avoid resubmitting the form
        return redirect('update_price_increment')

    return render(request, 'demo/travel_agency/update_price.html', {'increment_value': increment.increment_value})


@travel_agency_required
def update_exchange_rate(request):
    agency = travel_agency_profile_for_user(request.user)
    form = ExchangeRateForm(request.POST or None, instance=agency)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Exchange rate updated successfully.")
        return redirect("update_exchange_rate")

    return render(
        request,
        "demo/travel_agency/update_exchange_rate.html",
        {"form": form},
    )


def demo(request):
    if request.method != "POST":
        return render(
            request,
            "demo/home.html",
            flight_search_form_context(request.GET),
        )

    trip_type = normalize_trip_type(request.POST.get("tripType"))
    passenger_count = normalize_passenger_count(
        request.POST.get("passengerCount")
    )
    cabin_class = normalize_cabin(request.POST.get("cabinClassTop"))

    if trip_type == "multi-city":
        legs = posted_multi_city_legs(request)
        error = validate_multi_city_legs(legs)
        if error:
            messages.error(request, error)
            return render(
                request,
                "demo/home.html",
                flight_search_form_context(request.POST, legs),
            )

        raw_flights = []
        live_provider_reachable = False
        if (
            getattr(settings, "USE_LIVE_FLIGHT_API", True)
            and settings.FLIGHT_SEARCH_PROVIDER == "duffel"
        ):
            try:
                raw_flights = duffel_flight_search(
                    legs=legs,
                    passenger_count=passenger_count,
                    cabin=cabin_class,
                )
                live_provider_reachable = True
            except DuffelAPIError as error:
                logger.warning("Duffel multi-city search unavailable: %s", error)
        if not live_provider_reachable:
            raw_flights = local_multi_city_search(
                legs=legs,
                passenger_count=passenger_count,
                cabin=cabin_class,
                max_offers=getattr(settings, "MIN_FLIGHT_RESULTS", 18),
            )
            if raw_flights:
                messages.info(
                    request,
                    "Showing locally priced multi-city fares while live pricing is unavailable.",
                )
        origin = legs[0]["origin"]
        destination = legs[-1]["destination"]
        departure_date = legs[0]["departure_date"]
        return_date = legs[-1]["departure_date"]
        trip_purpose = ""
        route_title = "Multi-city trip"
        route_subtitle = " • ".join(
            f"{leg['origin']} → {leg['destination']}" for leg in legs
        )
    else:
        origin = normalize_iata(request.POST.get("Origin"))
        destination = normalize_iata(request.POST.get("Destination"))
        departure_date = request.POST.get("Departuredate")
        return_date = (
            request.POST.get("Returndate")
            if trip_type == "round-trip"
            else None
        )
        error = validate_standard_flight_search(
            origin,
            destination,
            departure_date,
            return_date,
            trip_type,
        )
        if error:
            messages.error(request, error)
            return render(
                request,
                "demo/home.html",
                flight_search_form_context(request.POST),
            )

        kwargs = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date,
            "adults": passenger_count,
            "travelClass": cabin_class,
        }
        if return_date:
            kwargs["returnDate"] = return_date

        raw_flights = []
        live_provider_reachable = False
        trip_purpose = ""
        live_flight_api_enabled = getattr(
            settings, "USE_LIVE_FLIGHT_API", True
        )
        if live_flight_api_enabled:
            try:
                if settings.FLIGHT_SEARCH_PROVIDER == "duffel":
                    search_legs = [{
                        "origin": origin,
                        "destination": destination,
                        "departure_date": departure_date,
                    }]
                    if return_date:
                        search_legs.append({
                            "origin": destination,
                            "destination": origin,
                            "departure_date": return_date,
                        })
                    raw_flights = duffel_flight_search(
                        legs=search_legs,
                        passenger_count=passenger_count,
                        cabin=cabin_class,
                    )
                else:
                    search_flights = amadeus.shopping.flight_offers_search.get(
                        **kwargs
                    )
                    raw_flights = list(search_flights.data)
                live_provider_reachable = True
            except Exception as error:
                logger.warning(
                    "%s flight search unavailable, using local fares: %s",
                    settings.FLIGHT_SEARCH_PROVIDER.title(),
                    error,
                )

        if return_date and live_flight_api_enabled and settings.FLIGHT_SEARCH_PROVIDER == "amadeus":
            try:
                trip_purpose_response = (
                    amadeus.travel.predictions.trip_purpose.get(
                        originLocationCode=origin,
                        destinationLocationCode=destination,
                        departureDate=departure_date,
                        returnDate=return_date,
                    ).data
                )
                trip_purpose = trip_purpose_response["result"]
            except Exception as error:
                logger.warning("Trip purpose lookup unavailable: %s", error)

        if not live_provider_reachable:
            raw_flights = local_flight_search(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                passenger_count=passenger_count,
                cabin=cabin_class,
            )
            if raw_flights:
                messages.info(
                    request,
                    "Showing locally priced fares while live airline pricing is unavailable.",
                )
        route_title = f"{origin} to {destination}"
        route_subtitle = ""

    for flight in raw_flights:
        flight["tripType"] = trip_type

    exchange_rate = exchange_rate_for_user(request.user)
    search_flights_returned = [
        Flight(flight, exchange_rate=exchange_rate).construct_flights()
        for flight in raw_flights
    ]
    if not search_flights_returned:
        messages.info(request, "No flight itinerary was found for this trip.")
        return render(
            request,
            "demo/home.html",
            flight_search_form_context(
                request.POST,
                posted_multi_city_legs(request)
                if trip_type == "multi-city"
                else None,
            ),
        )

    return render(
        request,
        "demo/results.html",
        {
            "response": zip(search_flights_returned, raw_flights),
            "origin": origin,
            "destination": destination,
            "departureDate": departure_date,
            "returnDate": return_date,
            "tripPurpose": trip_purpose,
            "trip_type": trip_type,
            "route_title": route_title,
            "route_subtitle": route_subtitle,
        },
    )


def normalize_trip_type(value):
    trip_type = str(value or "round-trip").strip().lower()
    return trip_type if trip_type in {"one-way", "round-trip", "multi-city"} else "round-trip"


def normalize_passenger_count(value):
    try:
        return min(max(int(value or 1), 1), 9)
    except (TypeError, ValueError):
        return 1


def posted_multi_city_legs(request):
    origins = request.POST.getlist("multi_origin")
    destinations = request.POST.getlist("multi_destination")
    departure_dates = request.POST.getlist("multi_date")
    return [
        {
            "origin": normalize_iata(origin),
            "destination": normalize_iata(destination),
            "departure_date": departure_date,
        }
        for origin, destination, departure_date in zip(
            origins,
            destinations,
            departure_dates,
        )
        if origin or destination or departure_date
    ][:5]


def validate_standard_flight_search(
    origin,
    destination,
    departure_date,
    return_date,
    trip_type,
):
    if len(origin) != 3 or len(destination) != 3:
        return "Choose valid origin and destination airports."
    if origin == destination:
        return "Origin and destination must be different."
    if not valid_future_date(departure_date):
        return "Choose a valid departure date that is not in the past."
    if trip_type == "round-trip":
        if not valid_future_date(return_date):
            return "Choose a valid return date."
        if return_date < departure_date:
            return "Return date cannot be before the departure date."
    return ""


def validate_multi_city_legs(legs):
    if len(legs) < 2:
        return "Add at least two flights for a multi-city trip."
    previous_date = None
    for index, leg in enumerate(legs, start=1):
        origin = leg["origin"]
        destination = leg["destination"]
        departure_date = leg["departure_date"]
        if len(origin) != 3 or len(destination) != 3:
            return f"Choose valid airports for flight {index}."
        if origin == destination:
            return f"Flight {index} must arrive at a different airport."
        if not valid_future_date(departure_date):
            return f"Choose a valid date for flight {index}."
        if previous_date and departure_date < previous_date:
            return "Multi-city flight dates must be in chronological order."
        previous_date = departure_date
    return ""


def valid_future_date(value):
    try:
        selected = datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False
    return selected >= datetime.now().date()


def flight_search_form_context(post_data=None, multi_legs=None):
    post_data = post_data or {}
    trip_type = normalize_trip_type(post_data.get("tripType"))
    legs = multi_legs or [
        {"origin": "", "destination": "", "departure_date": ""},
        {"origin": "", "destination": "", "departure_date": ""},
    ]
    return {
        "search_values": {
            "trip_type": trip_type,
            "origin": post_data.get("Origin", ""),
            "destination": post_data.get("Destination", ""),
            "departure_date": post_data.get("Departuredate", ""),
            "return_date": post_data.get("Returndate", ""),
            "passenger_count": normalize_passenger_count(
                post_data.get("passengerCount")
            ),
            "cabin": str(post_data.get("cabinClassTop") or "economy").lower(),
        },
        "multi_city_legs": legs,
    }


def cart_detail(request):
    items = visible_cart_items(request)
    flight_status_counts = flight_cart_state_counts(request, items)
    return render(
        request,
        "demo/cart.html",
        {
            "cart_items": items,
            "cart_total": cart_total_naira(request, items),
            "flight_status_counts": flight_status_counts,
            "flight_cart_count": sum(flight_status_counts.values()),
            "pending_cart_count": flight_status_counts["pending"],
            "has_removable_cart_items": has_removable_cart_items(request),
        },
    )


def cart_add_flight(request):
    if request.method != "POST":
        return redirect("home")

    flight_payload = request.POST.get("flight_data")
    try:
        flight_data = decode_flight_payload(flight_payload)
        added = add_flight_to_cart(request, flight_data)
        if added:
            messages.success(request, "Flight added to your cart.")
        else:
            messages.info(request, "That flight is already in your cart.")
    except (TypeError, ValueError, KeyError, IndexError, SyntaxError) as error:
        logger.warning("Could not add flight to cart: %s", error)
        messages.error(request, "We could not add that flight to your cart.")

    return redirect_after_cart_action(request, "cart_detail")


def cart_add_hotel(request):
    if request.method != "POST":
        return redirect("hotel")

    try:
        offer_id = request.POST.get("offer_id")
        hotel_data = {
            "offer_id": offer_id,
            "hotel_name": request.POST.get("hotel_name"),
            "description": request.POST.get("description"),
            "check_in": request.POST.get("check_in"),
            "check_out": request.POST.get("check_out"),
            "guests": request.POST.get("guests"),
            "price": request.POST.get("price"),
            "price_verified": False,
        }
        if (
            is_local_hotel_offer_id(offer_id)
            and request.user.is_authenticated
        ):
            hotel_details = local_hotel_offer(offer_id)
            offer = hotel_details["offers"][0]
            room = offer.get("room", {})
            hotel_data.update({
                "hotel_name": hotel_details.get("hotel", {}).get(
                    "name",
                    "Hotel stay",
                ),
                "description": room.get("description", {}).get("text")
                or room.get("type", "Hotel room"),
                "check_in": offer.get("checkInDate", ""),
                "check_out": offer.get("checkOutDate", ""),
                "guests": offer.get("guests", {}).get("adults", 1),
                "price": format_price_naira(
                    offer.get("price", {}).get("total", "0"),
                    offer.get("price", {}).get("currency", "USD"),
                    exchange_rate=exchange_rate_for_user(request.user),
                ),
                "price_verified": True,
            })
        added = add_hotel_to_cart(
            request,
            hotel_data,
        )
        if added:
            messages.success(request, "Hotel room added to your cart.")
        else:
            messages.info(request, "That hotel room is already in your cart.")
    except (TypeError, ValueError) as error:
        logger.warning("Could not add hotel to cart: %s", error)
        messages.error(request, "We could not add that hotel room to your cart.")

    return redirect_after_cart_action(request, "cart_detail")


def cart_remove(request, item_id):
    if request.method == "POST":
        if cart_item_is_submitted(request, item_id):
            messages.info(
                request,
                "Submitted flight requests remain in your cart until booking is complete.",
            )
        elif remove_cart_item(request, item_id):
            messages.success(request, "Item removed from your cart.")
        else:
            messages.info(request, "That item is no longer in your cart.")
    return redirect("cart_detail")


def cart_clear(request):
    if request.method == "POST":
        if clear_cart(request):
            messages.success(request, "Your saved cart items have been cleared.")
        elif any(
            item.get("type") == "flight"
            and item.get("cart_state") in {"pending", "approved"}
            for item in visible_cart_items(request)
        ):
            messages.info(
                request,
                "Submitted flight requests remain in your cart until booking is complete.",
            )
        else:
            messages.info(request, "Your cart is already empty.")
    return redirect("cart_detail")


def decode_flight_payload(flight_payload):
    if not flight_payload:
        raise ValueError("No flight data was provided.")

    decoded = urllib.parse.unquote_plus(flight_payload)
    try:
        flight_data = json.loads(decoded)
    except (json.JSONDecodeError, TypeError):
        flight_data = ast.literal_eval(decoded)

    if not isinstance(flight_data, dict):
        raise ValueError("Flight data must be an object.")
    return flight_data


def redirect_after_cart_action(request, default_url_name):
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(default_url_name)


def get_access_token():
    try:
        # Determine API endpoint based on hostname
        if settings.AMADEUS_HOSTNAME == 'production':
            api_endpoint = "https://api.amadeus.com/v1/security/oauth2/token"
        else:
            api_endpoint = "https://test.api.amadeus.com/v1/security/oauth2/token"

        response = requests.post(
            api_endpoint,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.AMADEUS_CLIENT_ID,
                "client_secret": settings.AMADEUS_CLIENT_SECRET,
            },
            timeout=settings.FLIGHT_SEARCH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        token_data = response.json()
        return token_data["access_token"]
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get access token: {str(e)}")
        raise Exception(f"Failed to get access token: {str(e)}")


def complete_flight_booking(request, flight_request, cart_item_id=None):
    flight_request.booking_completed_at = timezone.now()
    flight_request.save(update_fields=["booking_completed_at"])
    if cart_item_id:
        remove_cart_item(
            request,
            cart_item_id,
            allow_submitted=True,
        )


@staff_required
def book_flight(request):
    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('home')

    try:
        # Get flight data from POST
        cart_item_id = request.POST.get('cart_item_id')
        cart_item = None
        flight = request.POST.get('flight_data')
        if cart_item_id and not flight:
            cart_item = get_cart_item(request, cart_item_id)
            if not cart_item or cart_item.get('type') != 'flight':
                messages.error(request, "That flight is no longer in your cart.")
                return redirect('cart_detail')
            flight_data = cart_item.get('payload')
        else:
            flight_data = None

        if not flight:
            if flight_data is None:
                messages.error(request, "No flight data provided")
                return redirect('home')
        else:
            try:
                flight_data = decode_flight_payload(flight)
            except (TypeError, ValueError, KeyError, SyntaxError) as error:
                logger.warning("Failed to parse flight data: %s", error)
                messages.error(request, "Invalid flight data format")
                return redirect('home')

        logger.debug(f"Processing flight data: {type(flight_data)}")

        # Extract flight details from the flight data
        trip_type = normalize_trip_type(
            flight_data.get(
                "tripType",
                "round-trip"
                if len(flight_data.get("itineraries", [])) > 1
                else "one-way",
            )
        )
        route = flight_route_details(flight_data, trip_type=trip_type)
        origin = route['origin']
        destination = route['destination']
        departure_date = route['departure_at'].split('T')[0]
        return_date = (
            route['return_at'].split('T')[0]
            if route['return_at']
            else None
        )
        passenger_count = len(flight_data['travelerPricings'])
        travel_class = flight_data['travelerPricings'][0]['fareDetailsBySegment'][0]['cabin']
        staff_profile = staff_profile_for_user(request.user)
        organization = staff_profile.organization if staff_profile else None
        travel_agency = organization.travel_agency if organization else None
        exchange_rate = exchange_rate_for_agency(travel_agency)
        price_in_local_currency = float(
            flight_price_naira(
                flight_data,
                exchange_rate=exchange_rate,
            )
        )
        if cart_item and cart_item.get('cart_state') in {'pending', 'approved'}:
            quoted_price = cart_item.get('summary', {}).get('price')
            try:
                price_in_local_currency = float(
                    Decimal(str(quoted_price).replace(',', ''))
                )
            except (InvalidOperation, TypeError, ValueError, AttributeError):
                pass
        assigned_admin = first_organization_admin(organization)

        user_requests = Flight_model.objects.filter(
            user=request.user,
            booking_completed_at__isnull=True,
        )
        request_matches = user_requests.filter(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date if return_date else None,
            passenger_count=passenger_count,
            travel_class__iexact=travel_class,
            price=price_in_local_currency,
        )

        linked_request_id = (
            cart_item.get('flight_request_id') if cart_item else None
        )
        if linked_request_id:
            existing_flight = user_requests.filter(
                pk=linked_request_id,
            ).first()
            if not existing_flight:
                messages.error(
                    request,
                    "The approval record for this cart item is no longer valid.",
                )
                return redirect('cart_detail')
        else:
            # A previous approval for an identical itinerary must never approve a
            # new request. Only reuse the user's still-pending request.
            existing_flight = request_matches.filter(
                approved=False,
            ).order_by('-pk').first()

        # If the flight doesn't exist, create it
        if not existing_flight:
            flight_request = Flight_model.objects.create(
                user=request.user,
                requested_by_staff=staff_profile,
                organization=organization,
                travel_agency=travel_agency,
                assigned_admin=assigned_admin,
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date if return_date else None,
                passenger_count=passenger_count,
                travel_class=travel_class,
                price=price_in_local_currency,
                booking_payload=flight_data,
            )
        else:
            flight_request = existing_flight
            changed_fields = []
            canonical_fields = {
                'origin': origin,
                'destination': destination,
                'departure_date': departure_date,
                'return_date': return_date,
            }
            for field_name, canonical_value in canonical_fields.items():
                current_value = getattr(flight_request, field_name)
                comparable_value = (
                    current_value.isoformat()
                    if hasattr(current_value, 'isoformat')
                    else current_value
                )
                if comparable_value != canonical_value:
                    setattr(flight_request, field_name, canonical_value)
                    changed_fields.append(field_name)
            if staff_profile and not flight_request.requested_by_staff_id:
                flight_request.requested_by_staff = staff_profile
                changed_fields.append('requested_by_staff')
            if organization and not flight_request.organization_id:
                flight_request.organization = organization
                changed_fields.append('organization')
            if travel_agency and flight_request.travel_agency_id != travel_agency.id:
                flight_request.travel_agency = travel_agency
                changed_fields.append('travel_agency')
            if assigned_admin and not flight_request.assigned_admin_id:
                flight_request.assigned_admin = assigned_admin
                changed_fields.append('assigned_admin')
            if flight_request.booking_payload != flight_data:
                flight_request.booking_payload = flight_data
                changed_fields.append('booking_payload')
            if changed_fields:
                flight_request.save(update_fields=changed_fields)

        print(f"Extracted flight details: departure_date={departure_date}, return_date={return_date}, "
              f"passenger_count={passenger_count}, travel_class={travel_class}, "
              f"origin={origin}, destination={destination}")

        # Booking is authorized only by the exact request linked to this cart
        # item, never by another approved request with matching itinerary data.
        approved_flights = [flight_request] if flight_request.approved else []

        if approved_flights:
            for approved_flight in approved_flights:
                user = request.user

                if flight_data.get('source') in LOCAL_FARE_SOURCES:
                    passenger_name_record = [
                        local_booking_confirmation(
                            user,
                            flight_data,
                            exchange_rate=exchange_rate,
                            confirmed_price=approved_flight.price,
                        )
                    ]
                    complete_flight_booking(
                        request,
                        approved_flight,
                        cart_item_id,
                    )
                    try:
                        send_flight_email(
                            user,
                            origin,
                            destination,
                            departure_date,
                            return_date,
                            passenger_name_record,
                            travel_class,
                            approved_flight
                        )
                    except Exception as email_error:
                        logger.exception(
                            "Flight %s was booked but its confirmation email failed: %s",
                            approved_flight.pk,
                            email_error,
                        )
                        messages.warning(
                            request,
                            "Your flight was booked, but we could not send the confirmation email.",
                        )
                    return render(request, "demo/book_flight.html", {"response": passenger_name_record})

                if flight_data.get('source') == 'DUFFEL':
                    try:
                        emails_sent = send_flight_email_2(
                            user,
                            origin,
                            destination,
                            departure_date,
                            return_date,
                            travel_class,
                            approved_flight,
                        )
                        if not emails_sent:
                            raise RuntimeError(
                                "No booking email recipient is configured."
                            )
                    except Exception as email_error:
                        logger.exception(
                            "Could not email approved Duffel flight %s for user %s: %s",
                            approved_flight.pk,
                            user.username,
                            email_error,
                        )
                        messages.error(
                            request,
                            "We could not send this booking request. "
                            "Your approved flight remains in the cart so you can try again.",
                        )
                        return redirect('cart_detail')

                    complete_flight_booking(
                        request,
                        approved_flight,
                        cart_item_id,
                    )
                    return render(
                        request,
                        "demo/success_page.html",
                        {
                            "user": user,
                            "page_title": "Flight Booking Request Sent",
                            "booking_title": "Booking request sent!",
                            "booking_message": (
                                "Your approved flight details have been emailed "
                                "to the booking team."
                            ),
                            "button_text": "Go to Home",
                            "cart_count": cart_count(request),
                        },
                    )

                # Proceed with booking logic using the current user data
                try:
                    with transaction.atomic():
                        # Get access token
                        token = get_access_token()
                        headers = {
                            'Authorization': f'Bearer {token}',
                            'Content-Type': 'application/json'
                        }

                        # Prepare traveler information
                        traveler = {
                            "id": "1",
                            "dateOfBirth": "1982-01-16",
                            "name": {"firstName": "JORGE", "lastName": "GONZALES"},
                            "gender": "MALE",
                            "contact": {
                                "emailAddress": "jorge.gonzales833@telefonica.es",
                                "phones": [{"deviceType": "MOBILE", "countryCallingCode": "34", "number": "480080076"}],
                            },
                            "documents": [{
                                "documentType": "PASSPORT",
                                "birthPlace": "Madrid",
                                "issuanceLocation": "Madrid",
                                "issuanceDate": "2015-04-14",
                                "number": "00000000",
                                "expiryDate": "2025-04-14",
                                "issuanceCountry": "ES",
                                "validityCountry": "ES",
                                "nationality": "ES",
                                "holder": True,
                            }],
                        }

                        # Confirm flight pricing with Amadeus API
                        flight_price_confirmed = amadeus.shopping.flight_offers.pricing.post(
                            flight_data).data["flightOffers"]

                        if settings.AMADEUS_HOSTNAME == 'production':
                            booking_api_endpoint = "https://api.amadeus.com/v1/booking/flight-orders"
                        else:
                            booking_api_endpoint = "https://test.api.amadeus.com/v1/booking/flight-orders"

                        # Make booking via Amadeus API
                        response = requests.post(
                            booking_api_endpoint,
                            headers=headers,
                            json={"data": {
                                "type": "flight-order", "flightOffers": flight_price_confirmed, "travelers": [traveler]}},
                            timeout=settings.FLIGHT_SEARCH_TIMEOUT_SECONDS,
                        )
                        response.raise_for_status()

                        order = response.json()["data"]
                        passenger_name_record = [
                            Booking(
                                order,
                                exchange_rate=exchange_rate,
                                confirmed_price=approved_flight.price,
                            ).construct_booking()
                        ]

                        complete_flight_booking(
                            request,
                            approved_flight,
                            cart_item_id,
                        )
                        try:
                            send_flight_email(
                                user,
                                origin,
                                destination,
                                departure_date,
                                return_date,
                                passenger_name_record,
                                travel_class,
                                approved_flight
                            )
                        except Exception as email_error:
                            logger.exception(
                                "Flight %s was booked but its confirmation email failed: %s",
                                approved_flight.pk,
                                email_error,
                            )
                            messages.warning(
                                request,
                                "Your flight was booked, but we could not send the confirmation email.",
                            )
                        # Render the success page
                        return render(request, "demo/book_flight.html", {"response": passenger_name_record})

                except Exception as booking_error:
                    logger.exception(
                        "Could not complete approved flight %s for user %s: %s",
                        approved_flight.pk,
                        user.username,
                        booking_error,
                    )
                    messages.error(
                        request,
                        "We could not complete this booking. Your approved flight remains in the cart so you can try again.",
                    )
                    return redirect('cart_detail')

        else:
            logger.warning("No approved flights found")
            try:
                added_to_cart = add_flight_to_cart(
                    request,
                    flight_data,
                    flight_request.pk,
                )
            except ValueError as cart_error:
                logger.warning(
                    "Pending flight request could not be kept in the cart: %s",
                    cart_error,
                )
                messages.warning(
                    request,
                    f"Your flight is awaiting approval, but {cart_error}",
                )
            else:
                if added_to_cart:
                    messages.info(
                        request,
                        "Your flight is awaiting approval and has been added to your cart.",
                    )
                else:
                    messages.info(
                        request,
                        "Your flight is awaiting approval and remains in your cart.",
                    )

            # Send email notification about pending approval
            send_flight_pending_email(
                user=request.user,  # Current user requesting booking
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                passenger_count=passenger_count,
                travel_class=travel_class,
                price=price_in_local_currency,
                flight_request=flight_request
            )
            return redirect('cart_detail')

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        messages.error(request, f"Booking failed: {str(http_err)}")
    except Exception as error:
        logger.exception(f"An unexpected error occurred: {error}")
        messages.error(request, f"An error occurred: {str(error)}")

    return redirect('cart_detail' if cart_item_id else 'home')


def origin_airport_search(request):
    data = []
    term = request.GET.get("term", None)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        if getattr(settings, 'USE_LIVE_FLIGHT_API', True):
            try:
                if settings.FLIGHT_SEARCH_PROVIDER == 'duffel':
                    result = airport_suggestions(term)
                    return HttpResponse(
                        json.dumps(list(dict.fromkeys(result))),
                        content_type="application/json",
                    )
                data = amadeus.reference_data.locations.get(
                    keyword=term, subType=Location.ANY).data
            except Exception as error:
                logger.warning(
                    "%s origin autocomplete unavailable, using local airports: %s",
                    settings.FLIGHT_SEARCH_PROVIDER.title(),
                    error,
                )
                data = []
    result = get_city_airport_search_result(data, term)
    return HttpResponse(result, content_type="application/json")


def destination_airport_search(request):
    data = []
    term = request.GET.get("term", None)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        if getattr(settings, 'USE_LIVE_FLIGHT_API', True):
            try:
                if settings.FLIGHT_SEARCH_PROVIDER == 'duffel':
                    result = airport_suggestions(term)
                    return HttpResponse(
                        json.dumps(list(dict.fromkeys(result))),
                        content_type="application/json",
                    )
                data = amadeus.reference_data.locations.get(
                    keyword=term, subType=Location.ANY).data
            except Exception as error:
                logger.warning(
                    "%s destination autocomplete unavailable, using local airports: %s",
                    settings.FLIGHT_SEARCH_PROVIDER.title(),
                    error,
                )
                data = []
    result = get_city_airport_search_result(data, term)
    return HttpResponse(result, content_type="application/json")


def get_city_airport_search_result(data, term=None):
    result = get_city_airport_list(data)
    result.extend(local_airport_search(term))
    result = list(dict.fromkeys(result))
    return json.dumps(result)


def get_city_airport_list(data):
    result = []
    for i, val in enumerate(data):
        result.append(data[i]["iataCode"] + ", " + data[i]["name"])
    result = list(dict.fromkeys(result))
    return result


# ==========   TRAVEL AGENCY ============== >
def travel_agency_register(request):
    if request.method == 'POST':
        form = TravelAgencyUserCreationForm(request.POST)
        if form.is_valid():
            # Save the user but don't commit yet
            user = form.save(commit=False)
            user.is_active = True  # Allow the user to login, but without admin privileges
            user.save()  # Now save the user

            # Create a Profile for the user
            Profile.objects.create(user=user)
            approval_status = form.approval_code_is_valid()

            # Create the Travel Agency profile. A valid approval code approves it immediately.
            TravelAgency.objects.create(
                admin=user,
                first_name=user.first_name,
                last_name=user.last_name,
                phone=user.phone,  # Assuming phone is captured in the form
                company_code=form.cleaned_data.get('company_code') or None,
                approval_status=approval_status,
            )

            if approval_status:
                auth_login(request, user)
                messages.success(
                    request,
                    'Travel Agency registration successful. Your approval code was accepted.'
                )
                return redirect('travel_agency_approval_view')
            else:
                messages.success(
                    request,
                    'Travel Agency registration successful. Your account is awaiting approval from an approved Travel Agency.'
                )
                return redirect('travel_agency_login')
        else:
            messages.error(
                request, 'There was an error in the form. Please correct the errors.')
    else:
        form = TravelAgencyUserCreationForm()

    return render(request, 'demo/travel_agency/admin_register.html', {'form': form})


@never_cache
def travel_agency_login(request):
    if request.method == 'POST':
        form = TravelAgencyAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            if user is not None:
                try:
                    # Check if the user has a Travel Agency profile
                    agency_profile = TravelAgency.objects.get(admin=user)
                    company_code = form.cleaned_data.get('company_code')

                    if normalize_company_code(agency_profile.company_code) != company_code:
                        messages.error(request, 'Invalid company code.')
                        return render(request, 'demo/travel_agency/admin_login.html', {'form': form})

                    if not agency_profile.approval_status:
                        messages.error(
                            request, 'Your account is awaiting approval from an approved Travel Agency.')
                        return render(request, 'demo/travel_agency/admin_login.html', {'form': form})

                    # If approved, log in the Travel Agency user
                    auth_login(request, user)
                    return redirect('travel_agency_approval_view')

                except TravelAgency.DoesNotExist:
                    messages.error(request, 'You do not have admin access.')
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = TravelAgencyAuthenticationForm()

    return render(request, 'demo/travel_agency/admin_login.html', {'form': form})


@travel_agency_required
def travel_agency_organizations(request):
    agency_profile = get_object_or_404(
        TravelAgency, admin=request.user, approval_status=True)

    if request.method == 'POST':
        organization_id = request.POST.get('organization_id')
        action = request.POST.get('action')

        if action == 'toggle' and organization_id:
            organization = get_object_or_404(
                Organization,
                id=organization_id,
                travel_agency=agency_profile,
            )
            organization.active = not organization.active
            organization.save(update_fields=['active'])
            messages.success(request, f'{organization.name} has been updated.')
            return redirect('travel_agency_organizations')

        if action == 'claim' and organization_id:
            organization = get_object_or_404(
                Organization,
                id=organization_id,
                travel_agency__isnull=True,
            )
            organization.travel_agency = agency_profile
            organization.save(update_fields=['travel_agency'])
            Flight_model.objects.filter(
                organization=organization,
                travel_agency__isnull=True,
            ).update(travel_agency=agency_profile)
            messages.success(
                request, f'{organization.name} is now managed by your agency.')
            return redirect('travel_agency_organizations')

        if action == 'update' and organization_id:
            organization = get_object_or_404(
                Organization,
                id=organization_id,
                travel_agency=agency_profile,
            )
            form = TravelAgencyOrganizationForm(
                request.POST, instance=organization)
            if form.is_valid():
                form.save()
                messages.success(
                    request, f'{organization.name} has been updated.')
                return redirect('travel_agency_organizations')
            messages.error(request, 'Please correct the organization details.')
        else:
            form = TravelAgencyOrganizationForm(request.POST)
            if form.is_valid():
                organization = form.save(commit=False)
                organization.travel_agency = agency_profile
                organization.save()
                messages.success(
                    request, f'{organization.name} has been added.')
                return redirect('travel_agency_organizations')
            messages.error(request, 'Please correct the organization details.')
    else:
        form = TravelAgencyOrganizationForm()

    organizations = Organization.objects.filter(
        travel_agency=agency_profile,
    ).order_by('name')
    available_organizations = Organization.objects.filter(
        travel_agency__isnull=True,
    ).order_by('name')

    return render(
        request,
        'demo/travel_agency/organizations.html',
        {
            'form': form,
            'organizations': organizations,
            'available_organizations': available_organizations,
            'agency_profile': agency_profile,
        },
    )


@travel_agency_required
def travel_agency_approval_view(request):
    # Travel Agency users approve organization admin accounts.
    agency_profile = get_object_or_404(
        TravelAgency, admin=request.user, approval_status=True)
    pending_admins = Admin.objects.select_related(
        'admin',
        'organization',
    ).filter(
        approval_status=False,
    ).filter(
        Q(organization__travel_agency=agency_profile)
        | Q(organization__travel_agency__isnull=True)
        | Q(organization__isnull=True)
    )

    if request.method == 'POST':
        admin_id = request.POST.get('admin_id')
        action = request.POST.get('action')

        admin = get_object_or_404(pending_admins, id=admin_id)

        if action == 'approve':
            admin.approval_status = True
            admin.save()
            if admin.organization_id and admin.organization.travel_agency_id != agency_profile.id:
                admin.organization.travel_agency = agency_profile
                admin.organization.save(update_fields=['travel_agency'])
                Flight_model.objects.filter(
                    organization=admin.organization,
                    travel_agency__isnull=True,
                ).update(travel_agency=agency_profile)
            messages.success(
                request, f'{admin.admin.username} has been approved as an organization admin.')
        elif action == 'disapprove':
            admin.approval_status = False
            admin.save()
            messages.error(
                request, f'{admin.admin.username} has been disapproved.')

        return redirect('travel_agency_approval_view')

    return render(request, 'demo/travel_agency/admin_approval.html', {'pending_admins': pending_admins})


@travel_agency_required
def travel_agency_peer_approval_view(request):
    agency_profile = get_object_or_404(
        TravelAgency, admin=request.user, approval_status=True)
    pending_agencies = TravelAgency.objects.select_related('admin').filter(
        approval_status=False
    ).exclude(id=agency_profile.id)

    if request.method == 'POST':
        agency_id = request.POST.get('agency_id')
        action = request.POST.get('action')
        pending_agency = get_object_or_404(pending_agencies, id=agency_id)

        if action == 'approve':
            pending_agency.approval_status = True
            pending_agency.save(update_fields=['approval_status'])
            messages.success(
                request,
                f'{pending_agency.admin.username} has been approved as a Travel Agency.'
            )
        elif action == 'disapprove':
            pending_agency.approval_status = False
            pending_agency.save(update_fields=['approval_status'])
            messages.error(
                request,
                f'{pending_agency.admin.username} remains unapproved.'
            )

        return redirect('travel_agency_peer_approval_view')

    return render(
        request,
        'demo/travel_agency/agency_approval.html',
        {'pending_agencies': pending_agencies},
    )


# Travel Agency Report
@travel_agency_required
def travel_agency_report(request):
    agency_profile = get_object_or_404(
        TravelAgency, admin=request.user, approval_status=True)
    managed_organizations = Organization.objects.filter(
        travel_agency=agency_profile)
    flights = Flight_model.objects.select_related(
        'user',
        'organization',
        'travel_agency',
    ).filter(
        Q(travel_agency=agency_profile)
        | Q(travel_agency__isnull=True, organization__travel_agency=agency_profile)
    )
    staff_members = Staff.objects.select_related('staff', 'organization').filter(
        organization__in=managed_organizations
    )
    admins = Admin.objects.select_related('admin', 'organization').filter(
        organization__in=managed_organizations
    )

    # Handle Export to CSV, Excel, or PDF
    if 'export' in request.GET:
        file_format = request.GET.get('export')
        if file_format == 'csv':
            return export_combined_to_csv(flights, staff_members, admins)
        elif file_format == 'excel':
            return export_combined_to_excel(flights, staff_members, admins)
        elif file_format == 'pdf':
            return export_combined_to_pdf(request, flights, staff_members, admins)

    return render(request, 'demo/travel_agency/report.html', {
        'flights': flights,
        'staff_members': staff_members,
        'admins': admins,
        'managed_organizations': managed_organizations,
        'agency_profile': agency_profile,
    })


@travel_agency_required
def travel_agency_approved_flights(request):
    agency_profile = get_object_or_404(
        TravelAgency, admin=request.user, approval_status=True)
    approved_flight_requests = Flight_model.objects.select_related(
        'user',
        'organization',
        'travel_agency',
        'requested_by_staff__staff',
        'approved_by_admin__admin',
    ).filter(
        Q(travel_agency=agency_profile)
        | Q(travel_agency__isnull=True, organization__travel_agency=agency_profile),
        approved=True,
    ).order_by('-departure_date', '-id')

    return render(request, 'demo/travel_agency/approved_flights.html', {
        'approved_flights': approved_flight_requests,
        'agency_profile': agency_profile,
    })


def flight_admin_recipients(flight_request, fallback_roles=None):
    if flight_request:
        recipients = flight_request.organization_admin_emails()
        if recipients:
            return recipients
    return role_recipients(fallback_roles or settings.BOOKING_NOTIFICATION_RECIPIENT_ROLES)


def flight_requester_recipients(flight_request):
    if not flight_request:
        return []
    return flight_request.requester_emails()


def flight_agency_recipients(flight_request):
    if not flight_request:
        return []
    travel_agency = flight_request.mapped_travel_agency()
    if not travel_agency:
        return []
    return Flight_model.unique_emails([travel_agency.admin.email])


def flight_approval_recipients(flight_request):
    recipients = []
    recipients.extend(flight_requester_recipients(flight_request))
    recipients.extend(flight_agency_recipients(flight_request))
    return Flight_model.unique_emails(recipients)


def flight_booking_recipients(flight_request):
    recipients = []
    if flight_request:
        recipients.extend(flight_request.organization_admin_emails())
        recipients.extend(flight_agency_recipients(flight_request))

    if not recipients:
        recipients.extend(role_recipients(
            settings.BOOKING_NOTIFICATION_RECIPIENT_ROLES))

    return Flight_model.unique_emails(recipients)


def flight_email_context(flight_request):
    return {
        'user': flight_request.requesting_user(),
        'origin': flight_request.origin,
        'destination': flight_request.destination,
        'departure_date': flight_request.departure_date,
        'return_date': flight_request.return_date,
        'passenger_count': flight_request.passenger_count,
        'travel_class': flight_request.travel_class,
        'price': flight_request.price,
        'organization': flight_request.organization,
        'travel_agency': flight_request.mapped_travel_agency(),
    }


def send_flight_approval_email(flight_request):
    recipients = flight_approval_recipients(flight_request)
    if not recipients:
        return

    send_html_email(
        'Your Flight Booking Has Been Approved',
        'demo/email/flight_approval_email.html',
        flight_email_context(flight_request),
        recipients,
    )


def send_flight_email(user, origin, destination, departure_date, return_date, passenger_name_record, travel_class=None, flight_request=None):
    # Get user profile details
    first_name = user.first_name
    last_name = user.last_name
    email = user.email
    phone = user.phone

    # Prepare the email subject and message
    subject = 'Flight Order From Online Booking Tool'
    context = {
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'phone': phone,
        'origin': origin,
        'destination': destination,
        'departure_date': departure_date,
        'return_date': return_date,
        'travel_class': travel_class,
        'response': passenger_name_record
    }
    if flight_request:
        context.update({
            'passenger_count': flight_request.passenger_count,
            'price': flight_request.price,
            'organization': flight_request.organization,
            'travel_agency': flight_request.mapped_travel_agency(),
        })

    send_html_email(
        subject,
        'demo/email/flight_booking_email.html',
        context,
        flight_booking_recipients(flight_request),
    )
    print("Email sent successfully!")


def send_flight_email_2(user, origin, destination, departure_date, return_date, travel_class=None, flight_request=None):
    # Get user profile details
    first_name = user.first_name
    last_name = user.last_name
    email = user.email
    phone = user.phone

    # Prepare the email subject and message
    subject = 'Flight Order From Online Booking Tool'
    context = {
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'phone': phone,
        'origin': origin,
        'destination': destination,
        'departure_date': departure_date,
        'return_date': return_date,
        'travel_class': travel_class

    }
    if flight_request:
        context.update({
            'passenger_count': flight_request.passenger_count,
            'price': flight_request.price,
            'organization': flight_request.organization,
            'travel_agency': flight_request.mapped_travel_agency(),
        })

    sent_count = send_html_email(
        subject,
        'demo/email/flight_booking_email.html',
        context,
        flight_booking_recipients(flight_request),
    )
    if sent_count:
        print("Email sent successfully!")
    return sent_count


def send_flight_pending_email(user, origin, destination, departure_date, return_date, passenger_count, travel_class, price, flight_request=None):
    subject = "Flight Approval Pending"

    context = {
        "user": user,
        "origin": origin,
        "destination": destination,
        "departure_date": departure_date,
        "return_date": return_date,
        "passenger_count": passenger_count,
        "travel_class": travel_class,
        "price": price,
        "organization": flight_request.organization if flight_request else None,
        "travel_agency": flight_request.mapped_travel_agency() if flight_request else None,
    }

    send_html_email(
        subject,
        "demo/email/flight_pending_email.html",
        context,
        flight_admin_recipients(
            flight_request,
            settings.FLIGHT_APPROVAL_REQUEST_RECIPIENT_ROLES,
        ),
    )
    print("Email sent successfully!")


# ===========  HOTEL ===============>


def hotel(request):
    if request.method != 'POST':
        return render(
            request,
            'demo/hotel/demo_form.html',
            hotel_search_form_context(request.GET),
        )

    origin = normalize_city_code(request.POST.get('Origin'))
    checkinDate = request.POST.get('Checkindate')
    checkoutDate = request.POST.get('Checkoutdate')
    exchange_rate = exchange_rate_for_user(request.user)

    try:
        guest_count = min(
            max(int(request.POST.get('guestCount', '1') or 1), 1),
            9,
        )
    except (TypeError, ValueError):
        guest_count = 1

    validation_error = validate_hotel_search(
        origin,
        checkinDate,
        checkoutDate,
    )
    if validation_error:
        messages.error(request, validation_error)
        return render(
            request,
            'demo/hotel/demo_form.html',
            hotel_search_form_context(request.POST),
        )

    if origin and checkinDate and checkoutDate:
        # Store guest count in session for later use during booking
        request.session['guest_count'] = guest_count

        raw_hotels = []
        live_search_attempted = False
        live_search_failed = False
        live_hotel_api_enabled = getattr(
            settings,
            'USE_LIVE_HOTEL_API',
            getattr(settings, 'USE_LIVE_FLIGHT_API', True)
        )
        hotel_search_provider = getattr(
            settings,
            'HOTEL_SEARCH_PROVIDER',
            'amadeus',
        ).strip().lower()

        if live_hotel_api_enabled and hotel_search_provider == 'amadeus':
            live_search_attempted = True
            try:
                hotel_list = amadeus.reference_data.locations.hotels.by_city.get(
                    cityCode=origin)
                hotel_ids = [
                    hotel_item['hotelId']
                    for hotel_item in hotel_list.data
                    if hotel_item.get('hotelId')
                ]
                num_hotels = 40
                if hotel_ids:
                    search_hotels = amadeus.shopping.hotel_offers_search.get(
                        hotelIds=hotel_ids[0:num_hotels],
                        checkInDate=checkinDate,
                        checkOutDate=checkoutDate,
                        adults=guest_count,
                    )
                    raw_hotels = list(search_hotels.data)
            except Exception as error:
                live_search_failed = True
                logger.warning(
                    "Amadeus hotel search unavailable, using standalone hotels: %s",
                    error,
                )

        minimum_results = getattr(
            settings, 'MIN_HOTEL_RESULTS', LOCAL_HOTEL_RESULTS_TARGET)
        using_standalone_hotels = not raw_hotels
        if using_standalone_hotels:
            raw_hotels = local_hotel_search(
                city_code=origin,
                checkin_date=checkinDate,
                checkout_date=checkoutDate,
                guest_count=guest_count,
                max_results=minimum_results,
            )
            if raw_hotels:
                if live_search_failed:
                    fallback_message = (
                        "Live hotel search is unavailable. "
                        "Showing standalone hotel inventory instead."
                    )
                elif live_search_attempted:
                    fallback_message = (
                        "No live hotel inventory was returned. "
                        "Showing standalone hotel inventory instead."
                    )
                else:
                    fallback_message = "Showing standalone hotel inventory."
                messages.info(
                    request,
                    fallback_message,
                )

        hotel_offers, hotel_results = construct_hotel_results(
            raw_hotels,
            exchange_rate=exchange_rate,
        )

        # A provider can return records that do not contain usable room offers.
        # Treat that as an unusable live response and fall back as well.
        if not hotel_offers and not using_standalone_hotels:
            raw_hotels = local_hotel_search(
                city_code=origin,
                checkin_date=checkinDate,
                checkout_date=checkoutDate,
                guest_count=guest_count,
                max_results=minimum_results,
            )
            hotel_offers, hotel_results = construct_hotel_results(
                raw_hotels,
                exchange_rate=exchange_rate,
            )
            if hotel_offers:
                messages.info(
                    request,
                    "Live hotel results could not be displayed. "
                    "Showing standalone hotel inventory instead.",
                )

        if not hotel_offers:
            messages.info(request, "No hotels found in this location.")
            return render(
                request,
                'demo/hotel/demo_form.html',
                hotel_search_form_context(request.POST),
            )

        response = zip(hotel_offers, hotel_results)
        return render(request, 'demo/hotel/results.html', {'response': response,
                                                           'origin': hotel_city_label(origin),
                                                           'departureDate': checkinDate,
                                                           'returnDate': checkoutDate,
                                                           'guest_count': guest_count,
                                                           })
    return render(
        request,
        'demo/hotel/demo_form.html',
        hotel_search_form_context(request.POST),
    )


def construct_hotel_results(raw_hotels, exchange_rate=None):
    hotel_offers = []
    hotel_results = []
    for hotel_data in raw_hotels:
        offer = Hotel(
            hotel_data,
            exchange_rate=exchange_rate,
        ).construct_hotel()
        if offer:
            hotel_offers.append(offer)
            hotel_results.append(hotel_data)
    return hotel_offers, hotel_results


def validate_hotel_search(origin, checkin_date, checkout_date):
    if len(str(origin or '')) != 3:
        return "Choose a valid hotel destination."
    if not valid_future_date(checkin_date):
        return "Choose a valid check-in date that is not in the past."
    if not valid_future_date(checkout_date):
        return "Choose a valid check-out date."
    if checkout_date <= checkin_date:
        return "Check-out must be after check-in."
    return ""


def hotel_search_form_context(values=None):
    values = values or {}
    try:
        guests = min(max(int(values.get('guestCount', 1) or 1), 1), 9)
    except (TypeError, ValueError):
        guests = 1
    return {
        'hotel_search_values': {
            'origin': values.get('Origin', ''),
            'checkin': values.get('Checkindate', ''),
            'checkout': values.get('Checkoutdate', ''),
            'guests': guests,
        }
    }


def rooms_per_hotel(request, hotel, departureDate, returnDate):
    try:
        guest_count = request.session.get('guest_count', 1)
        if is_local_hotel_id(hotel):
            rooms = local_room_search(
                hotel, departureDate, returnDate, guest_count)
        else:
            # Search for rooms in a given hotel
            rooms = amadeus.shopping.hotel_offers_search.get(hotelIds=hotel,
                                                             checkInDate=departureDate,
                                                             checkOutDate=returnDate,
                                                             adults=guest_count).data
        hotel_rooms = Room(
            rooms,
            exchange_rate=exchange_rate_for_user(request.user),
        ).construct_room()
        try:
            stay_nights = max(
                (
                    datetime.strptime(returnDate, '%Y-%m-%d').date()
                    - datetime.strptime(departureDate, '%Y-%m-%d').date()
                ).days,
                1,
            )
        except (TypeError, ValueError):
            stay_nights = 1
        return render(request, 'demo/hotel/rooms_per_hotel.html', {'response': hotel_rooms,
                                                                   'name': rooms[0]['hotel']['name'],
                                                                   'departureDate': departureDate,
                                                                   'returnDate': returnDate,
                                                                   'guest_count': guest_count,
                                                                   'stay_nights': stay_nights,
                                                                   })
    except (TypeError, AttributeError, ResponseError, KeyError, IndexError, ValueError) as error:
        messages.add_message(request, messages.ERROR, error)
        return render(request, 'demo/hotel/rooms_per_hotel.html', {})


def send_hotel_booking_email(
    user,
    hotel_details,
    booking_details,
    exchange_rate=None,
    confirmed_price=None,
):
    subject = "Hotel Booking Confirmation from Online Booking Tool"
    from_email = settings.EMAIL_HOST_USER
    to_email = role_recipients(
        settings.HOTEL_BOOKING_NOTIFICATION_RECIPIENT_ROLES)

    # Render the HTML template and strip it to plain text
    total_price = (
        str(confirmed_price)
        if confirmed_price is not None
        else format_price_naira(
            hotel_details['offers'][0]['price']['total'],
            hotel_details['offers'][0]['price'].get('currency', 'USD'),
            exchange_rate=exchange_rate,
        )
    )
    html_content = render_to_string("demo/email/hotel_booking_email.html", {
        "user": user,
        "hotel_name": hotel_details['hotel']['name'],
        "check_in_date": hotel_details['offers'][0]['checkInDate'],
        "check_out_date": hotel_details['offers'][0]['checkOutDate'],
        "room_type": hotel_details['offers'][0]['room']['type'],
        "booking_id": booking_details[0]['id'],
        "confirmation_id": booking_details[0]['providerConfirmationId'],
        "total_price": total_price,
        "currency": "₦"
    })
    text_content = strip_tags(html_content)

    # Create the email object
    email = EmailMultiAlternatives(subject, text_content, from_email, to_email)
    email.attach_alternative(html_content, "text/html")

    # Send the email
    try:
        email.send(fail_silently=False)
        print("Hotel booking confirmation email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {str(e)}")


def hotel_booking_success_context():
    return {
        "page_title": "Hotel Booking Successful",
        "booking_title": "Hotel Booking Successful!",
        "booking_message": "Your hotel has been successfully booked. Please check your email for the booking confirmation.",
        "button_text": "Go to Home",
    }


@staff_required
def book_hotel(request, offer_id):
    if request.method != "POST":
        messages.error(request, "Choose a room before booking.")
        return redirect("hotel")

    try:
        cart_item_id = request.POST.get("cart_item_id")
        cart_item = None
        if cart_item_id:
            cart_item = get_cart_item(request, cart_item_id)
            if not cart_item or cart_item.get("type") != "hotel":
                messages.error(request, "That hotel room is no longer in your cart.")
                return redirect("cart_detail")
            stored_offer_id = cart_item.get("payload", {}).get("offer_id")
            if stored_offer_id != offer_id:
                messages.error(request, "The hotel offer in your cart has changed.")
                return redirect("cart_detail")

        if is_local_hotel_offer_id(offer_id):
            hotel_details = local_hotel_offer(offer_id)
            booking_details = local_hotel_booking_confirmation(
                request.user,
                offer_id,
            )
            send_hotel_booking_email(
                request.user,
                hotel_details,
                booking_details,
                exchange_rate=exchange_rate_for_user(request.user),
                confirmed_price=(
                    cart_item.get("summary", {}).get("price")
                    if cart_item
                    and cart_item.get("summary", {}).get("price_verified")
                    else None
                ),
            )

        if cart_item_id:
            remove_cart_item(request, cart_item_id)

        context = hotel_booking_success_context()
        context["cart_count"] = cart_count(request)
        return render(request, "demo/success_page.html", context)
    except Exception as error:
        messages.add_message(request, messages.ERROR, str(error))
        return render(request, "demo/success_page.html", hotel_booking_success_context())


def city_search(request):
    data = []
    term = request.GET.get('term', None)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        live_hotel_api_enabled = getattr(
            settings,
            'USE_LIVE_HOTEL_API',
            getattr(settings, 'USE_LIVE_FLIGHT_API', True)
        )
        hotel_search_provider = getattr(
            settings,
            'HOTEL_SEARCH_PROVIDER',
            'amadeus',
        ).strip().lower()
        if live_hotel_api_enabled and hotel_search_provider == 'amadeus':
            try:
                data = amadeus.reference_data.locations.get(keyword=term,
                                                            subType=Location.ANY).data
            except Exception as error:
                logger.warning(
                    f"Amadeus city autocomplete unavailable, using local hotel cities: {error}")
                data = []
    result = get_hotel_city_search_result(data, term)
    return HttpResponse(result, content_type='application/json')


def get_city_list(data):
    result = []
    for i, val in enumerate(data):
        result.append(data[i]['iataCode'] + ', ' + data[i]['name'])
    result = list(dict.fromkeys(result))
    return json.dumps(result)


def get_hotel_city_search_result(data, term=None):
    result = json.loads(get_city_list(data))
    result.extend(local_hotel_city_search(term))
    result = list(dict.fromkeys(result))
    return json.dumps(result)
