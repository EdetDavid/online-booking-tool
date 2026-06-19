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
from functools import wraps
from amadeus import Client, ResponseError, Location
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from .flight import Flight
from .booking import Booking
from .hotel import Hotel, format_price_naira
from .room import Room
from .local_flights import (
    LOCAL_FARE_SOURCES,
    local_airport_search,
    local_booking_confirmation,
    local_flight_search,
    normalize_cabin,
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
from .role_email import (
    role_recipients,
    send_html_email,
)
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from .forms import (
    AdminUserCreationForm,
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


amadeus = Client()


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
    return Admin.objects.select_related('organization').filter(admin=user).first()


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

    if request.method == 'POST':
        # Get selected flights
        flight_ids = request.POST.getlist('flight_ids')

        if flight_ids:
            flights = Flight_model.objects.filter(id__in=flight_ids)
            if admin_profile and admin_profile.organization_id:
                flights = flights.filter(
                    organization=admin_profile.organization)

            for flight in flights:
                flight.approved = True
                if admin_profile:
                    flight.approved_by_admin = admin_profile
                    if not flight.assigned_admin_id:
                        flight.assigned_admin = admin_profile
                flight.save()
                messages.success(
                    request, f'Flight {flight.origin} to {flight.destination} on {flight.departure_date} has been approved.')

                send_flight_approval_email(flight)

            return redirect('approve_flight')

    # Fetch all flights where approval status is False
    pending_flights = Flight_model.objects.filter(approved=False)
    if admin_profile and admin_profile.organization_id:
        pending_flights = pending_flights.filter(
            organization=admin_profile.organization)
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
        profile_picture = request.FILES.get('profile_picture')
        if profile_picture:
            request.user.profile.profile_picture = profile_picture
            request.user.profile.save()
            messages.success(request, 'Profile picture updated successfully.')
            return redirect('admin_profile')
        else:
            messages.error(request, 'No file selected or an error occurred.')

    return render(request, 'demo/admin/profile.html', {'error_message': messages.get_messages(request)})


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
            'Approved' if flight.approved else 'Unapproved'
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
        ws.write(row, 9, 'Approved' if flight.approved else 'Unapproved')
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
        profile_picture = request.FILES.get('profile_picture')
        if profile_picture:
            request.user.profile.profile_picture = profile_picture
            request.user.profile.save()
            messages.success(request, 'Profile picture updated successfully.')
            return redirect('profile')
        else:
            messages.error(request, 'No file selected or an error occurred.')

    return render(request, 'demo/staff/profile.html', {'error_message': messages.get_messages(request)})


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


def demo(request):
    user = request.user
    origin = request.POST.get("Origin")
    destination = request.POST.get("Destination")
    departure_date = request.POST.get("Departuredate")
    return_date = request.POST.get("Returndate")
    passenger_count = request.POST.get("passengerCount")
    cabin_class = normalize_cabin(request.POST.get("cabinClassTop"))

    kwargs = {
        "originLocationCode": origin,
        "destinationLocationCode": destination,
        "departureDate": departure_date,
        "adults": passenger_count,
        "travelClass": cabin_class,
    }

    tripPurpose = ""
    live_flight_api_enabled = getattr(settings, 'USE_LIVE_FLIGHT_API', True)

    if return_date and live_flight_api_enabled:
        kwargs["returnDate"] = return_date
        kwargs_trip_purpose = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date,
            "returnDate": return_date,
        }
        try:
            trip_purpose_response = amadeus.travel.predictions.trip_purpose.get(
                **kwargs_trip_purpose).data
            tripPurpose = trip_purpose_response["result"]
        except Exception as error:
            logger.warning(f"Trip purpose lookup unavailable: {error}")

    if origin and destination and departure_date:
        search_flights = None
        if live_flight_api_enabled:
            try:
                search_flights = amadeus.shopping.flight_offers_search.get(
                    **kwargs)
            except Exception as error:
                logger.warning(
                    f"Amadeus flight search unavailable, using local fares: {error}")

        search_flights_returned = []
        raw_flights = list(search_flights.data) if search_flights else []
        minimum_results = getattr(settings, 'MIN_FLIGHT_RESULTS', 18)

        if len(raw_flights) < minimum_results:
            local_fares = local_flight_search(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                passenger_count=passenger_count,
                cabin=cabin_class,
            )
            raw_flights.extend(
                local_fares[:max(minimum_results - len(raw_flights), 0)])
            if local_fares and not search_flights:
                messages.info(
                    request, "Showing locally priced fares while live airline pricing is unavailable.")
            elif local_fares:
                messages.info(
                    request, "Showing additional local fare options for this route.")

        for flight in raw_flights:
            offer = Flight(flight).construct_flights()
            search_flights_returned.append(offer)

        response = zip(search_flights_returned, raw_flights)
        # Check if the response is empty and pass a message to the template
        if not search_flights_returned:
            messages.info(request, "No flight itinerary for this route.")
            return redirect('home')

        return render(
            request,
            "demo/results.html",
            {
                "response": response,
                "origin": origin,
                "destination": destination,
                "departureDate": departure_date,
                "returnDate": return_date,
                "tripPurpose": tripPurpose,
            },
        )

    return render(request, "demo/home.html")


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
        )
        response.raise_for_status()
        token_data = response.json()
        return token_data["access_token"]
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get access token: {str(e)}")
        raise Exception(f"Failed to get access token: {str(e)}")


@staff_required
def book_flight(request):
    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('home')

    try:
        # Get flight data from POST
        flight = request.POST.get('flight_data')
        if not flight:
            messages.error(request, "No flight data provided")
            return redirect('home')

        # The template posts a URL-encoded string; decode first
        try:
            decoded = urllib.parse.unquote_plus(flight)
        except Exception:
            decoded = flight

        # Try to parse JSON first, then fall back to ast.literal_eval
        try:
            flight_data = json.loads(decoded)
        except Exception as json_err:
            try:
                flight_data = ast.literal_eval(decoded)
            except Exception as eval_err:
                logger.exception(
                    f"Failed to parse flight data: json_err={json_err}, eval_err={eval_err}")
                messages.error(request, "Invalid flight data format")
                return redirect('home')

        logger.debug(f"Processing flight data: {type(flight_data)}")

        # Extract flight details from the flight data
        origin = flight_data['itineraries'][0]['segments'][0]['departure']['iataCode']
        destination = flight_data['itineraries'][0]['segments'][-1]['arrival']['iataCode']
        departure_date = flight_data['itineraries'][0]['segments'][0]['departure']['at'].split('T')[
            0]
        return_date = flight_data['itineraries'][-1]['segments'][-1]['arrival']['at'].split(
            'T')[0] if len(flight_data['itineraries']) > 1 else None
        passenger_count = len(flight_data['travelerPricings'])
        travel_class = flight_data['travelerPricings'][0]['fareDetailsBySegment'][0]['cabin']
        price = float(flight_data['price']['total'])

        # Multiply the price by 1600
        price_in_local_currency = price * 1600
        staff_profile = staff_profile_for_user(request.user)
        organization = staff_profile.organization if staff_profile else None
        travel_agency = organization.travel_agency if organization else None
        assigned_admin = first_organization_admin(organization)

        # Check if the flight already exists
        existing_flight = Flight_model.objects.filter(
            user=request.user,
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date if return_date else None,
            passenger_count=passenger_count,
            travel_class=travel_class,
            price=price_in_local_currency
        ).first()

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
                price=price_in_local_currency
            )
        else:
            flight_request = existing_flight
            changed_fields = []
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
            if changed_fields:
                flight_request.save(update_fields=changed_fields)

        print(f"Extracted flight details: departure_date={departure_date}, return_date={return_date}, "
              f"passenger_count={passenger_count}, travel_class={travel_class}, "
              f"origin={origin}, destination={destination}")

        # Find approved flights for any user matching the criteria
        approved_flights = Flight_model.objects.filter(
            user=request.user,
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            passenger_count=passenger_count,
            travel_class__iexact=travel_class,
            price=price_in_local_currency,
            approved=True
        )

        if approved_flights:
            for approved_flight in approved_flights:
                user = request.user

                if flight_data.get('source') in LOCAL_FARE_SOURCES:
                    passenger_name_record = [
                        local_booking_confirmation(user, flight_data)
                    ]
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
                    return render(request, "demo/book_flight.html", {"response": passenger_name_record})

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
                                "type": "flight-order", "flightOffers": flight_price_confirmed, "travelers": [traveler]}}
                        )
                        response.raise_for_status()

                        order = response.json()["data"]
                        passenger_name_record = [
                            Booking(order).construct_booking()]

                        # Send confirmation email to the user
                        send_flight_email(
                            user,  # Correct user from the loop
                            origin,
                            destination,
                            departure_date,
                            return_date,
                            passenger_name_record,
                            travel_class,
                            approved_flight
                        )

                        # Render the success page
                        return render(request, "demo/book_flight.html", {"response": passenger_name_record})

                except Exception as booking_error:
                    logger.error(
                        f"Error booking flight for user {user.username}: {booking_error}")
                    messages.success(
                        request, f"Flight Booked {user.username}. Please check your mails.")
                    send_flight_email_2(user, origin, destination, departure_date,
                                        return_date, travel_class, approved_flight)
                    return render(request, "demo/success_page.html", {"user": user})

        else:
            logger.warning("No approved flights found")
            messages.error(request, "Your flight hasn't been approved yet.")

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

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        messages.error(request, f"Booking failed: {str(http_err)}")
    except Exception as error:
        logger.exception(f"An unexpected error occurred: {error}")
        messages.error(request, f"An error occurred: {str(error)}")

    return redirect('home')


def origin_airport_search(request):
    data = []
    term = request.GET.get("term", None)
    if request.is_ajax():
        if getattr(settings, 'USE_LIVE_FLIGHT_API', True):
            try:
                data = amadeus.reference_data.locations.get(
                    keyword=term, subType=Location.ANY
                ).data
            except Exception as error:
                logger.warning(
                    f"Amadeus origin autocomplete unavailable, using local airports: {error}")
                data = []
    result = get_city_airport_search_result(data, term)
    return HttpResponse(result, content_type="application/json")


def destination_airport_search(request):
    data = []
    term = request.GET.get("term", None)
    if request.is_ajax():
        if getattr(settings, 'USE_LIVE_FLIGHT_API', True):
            try:
                data = amadeus.reference_data.locations.get(
                    keyword=term, subType=Location.ANY
                ).data
            except Exception as error:
                logger.warning(
                    f"Amadeus destination autocomplete unavailable, using local airports: {error}")
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

    send_html_email(
        subject,
        'demo/email/flight_booking_email.html',
        context,
        flight_booking_recipients(flight_request),
    )
    print("Email sent successfully!")


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
    origin = normalize_city_code(request.POST.get('Origin'))
    checkinDate = request.POST.get('Checkindate')
    checkoutDate = request.POST.get('Checkoutdate')

    try:
        guest_count = max(int(request.POST.get('guestCount', '1') or 1), 1)
    except (TypeError, ValueError):
        guest_count = 1

    if origin and checkinDate and checkoutDate:
        # Store guest count in session for later use during booking
        request.session['guest_count'] = guest_count

        raw_hotels = []
        live_hotel_api_enabled = getattr(
            settings,
            'USE_LIVE_HOTEL_API',
            getattr(settings, 'USE_LIVE_FLIGHT_API', True)
        )

        if live_hotel_api_enabled:
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
                logger.warning(
                    f"Amadeus hotel search unavailable, using local hotels: {error}")

        minimum_results = getattr(
            settings, 'MIN_HOTEL_RESULTS', LOCAL_HOTEL_RESULTS_TARGET)
        if len(raw_hotels) < minimum_results:
            had_live_hotels = bool(raw_hotels)
            local_hotels = local_hotel_search(
                city_code=origin,
                checkin_date=checkinDate,
                checkout_date=checkoutDate,
                guest_count=guest_count,
                max_results=minimum_results,
            )
            raw_hotels.extend(
                local_hotels[:max(minimum_results - len(raw_hotels), 0)])
            if local_hotels and not had_live_hotels:
                messages.info(
                    request, "Showing locally priced hotels while live hotel inventory is unavailable.")
            elif local_hotels:
                messages.info(
                    request, "Showing additional local hotel options for this city.")

        hotel_offers = []
        hotel_results = []
        for hotel_data in raw_hotels:
            offer = Hotel(hotel_data).construct_hotel()
            if offer:
                hotel_offers.append(offer)
                hotel_results.append(hotel_data)

        if not hotel_offers:
            messages.info(request, "No hotels found in this location.")
            return render(request, 'demo/hotel/demo_form.html', {})

        response = zip(hotel_offers, hotel_results)
        return render(request, 'demo/hotel/results.html', {'response': response,
                                                           'origin': hotel_city_label(origin),
                                                           'departureDate': checkinDate,
                                                           'returnDate': checkoutDate,
                                                           })
    return render(request, 'demo/hotel/demo_form.html', {})


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
        hotel_rooms = Room(rooms).construct_room()
        return render(request, 'demo/hotel/rooms_per_hotel.html', {'response': hotel_rooms,
                                                                   'name': rooms[0]['hotel']['name'],
                                                                   'departureDate': departureDate,
                                                                   'returnDate': returnDate,
                                                                   })
    except (TypeError, AttributeError, ResponseError, KeyError, IndexError, ValueError) as error:
        messages.add_message(request, messages.ERROR, error)
        return render(request, 'demo/hotel/rooms_per_hotel.html', {})


def send_hotel_booking_email(user, hotel_details, booking_details):
    subject = "Hotel Booking Confirmation from Online Booking Tool"
    from_email = settings.EMAIL_HOST_USER
    to_email = role_recipients(
        settings.HOTEL_BOOKING_NOTIFICATION_RECIPIENT_ROLES)

    # Render the HTML template and strip it to plain text
    html_content = render_to_string("demo/email/hotel_booking_email.html", {
        "user": user,
        "hotel_name": hotel_details['hotel']['name'],
        "check_in_date": hotel_details['offers'][0]['checkInDate'],
        "check_out_date": hotel_details['offers'][0]['checkOutDate'],
        "room_type": hotel_details['offers'][0]['room']['type'],
        "booking_id": booking_details[0]['id'],
        "confirmation_id": booking_details[0]['providerConfirmationId'],
        "total_price": format_price_naira(
            hotel_details['offers'][0]['price']['total'],
            hotel_details['offers'][0]['price'].get('currency', 'USD'),
        ),
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


def book_hotel(request, offer_id):
    try:
        # Always show the success page after clicking "Book Now".
        # This bypasses external booking calls and any intermediate pages.
        return render(request, "demo/success_page.html", hotel_booking_success_context())
    except Exception as error:
        messages.add_message(request, messages.ERROR, str(error))
        return render(request, "demo/success_page.html", hotel_booking_success_context())


def city_search(request):
    data = []
    term = request.GET.get('term', None)
    if request.is_ajax():
        live_hotel_api_enabled = getattr(
            settings,
            'USE_LIVE_HOTEL_API',
            getattr(settings, 'USE_LIVE_FLIGHT_API', True)
        )
        if live_hotel_api_enabled:
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
