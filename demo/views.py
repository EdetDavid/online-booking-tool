from django.utils.html import strip_tags
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
import json
import ast
import urllib.parse
import csv
import xlwt
import logging
import requests
from amadeus import Client, ResponseError, Location
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .flight import Flight
from .booking import Booking
from .hotel import Hotel
from .room import Room
from .models import Admin, Staff, Profile, Flight_model, PriceIncrement, ThriveAdmin
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from .forms import AdminUserCreationForm, StaffUserCreationForm, ProfileForm, ThriveAdminUserCreationForm
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
logger = logging.getLogger(__name__)


amadeus = Client()


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

            # Create the Admin profile with approval_status = False (unapproved)
            Admin.objects.create(
                admin=user,
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


def admin_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
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
        form = AuthenticationForm()

    return render(request, 'demo/admin/admin_login.html', {'form': form})


def admin_approval_view(request):
    # Fetch all pending admins where approval_status is False
    pending_admins = Admin.objects.filter(approval_status=False)

    if request.method == 'POST':
        admin_id = request.POST.get('admin_id')
        action = request.POST.get('action')

        # Fetch the admin by ID
        admin = get_object_or_404(Admin, id=admin_id)

        if action == 'approve':
            admin.approval_status = True  # Approve the admin
            admin.save()
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


@login_required(login_url="admin_login")
def admin_dashboard(request):
    return render(request, 'demo/admin/base.html')


def coming_soon(request):
    """Render a simple coming soon page for unfinished nav links."""
    return render(request, 'demo/coming_soon.html')


@login_required(login_url='admin_login')
def approve_flight(request):
    if request.method == 'POST':
        # Get selected flights
        flight_ids = request.POST.getlist('flight_ids')

        if flight_ids:
            flights = Flight_model.objects.filter(id__in=flight_ids)

            for flight in flights:
                flight.approved = True
                flight.save()
                messages.success(
                    request, f'Flight {flight.origin} to {flight.destination} on {flight.departure_date} has been approved.')

                # Prepare email context
                email_context = {
                    'user': flight.user,  # Assuming the Flight model has a foreign key to User
                    'origin': flight.origin,
                    'destination': flight.destination,
                    'departure_date': flight.departure_date,
                }

                # Render the HTML email template
                email_body = render_to_string(
                    'demo/email/flight_approval_email.html', email_context)

                # Create email message
                email = EmailMultiAlternatives(
                    subject='Your Flight Booking Has Been Approved',
                    body='This is an HTML email. Please view it in a browser.',
                    from_email=settings.EMAIL_HOST_USER,
                    to=[flight.user.email],
                )

                # Attach the HTML body to the email
                email.attach_alternative(email_body, "text/html")
                email.send(fail_silently=False)
                print(f"Sent email to {flight.user.email}")

            return redirect('approve_flight')

    # Fetch all flights where approval status is False
    pending_flights = Flight_model.objects.filter(approved=False)
    return render(request, 'demo/admin/approve_flight.html', {'pending_flights': pending_flights})


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


def staff_list(request):
    profile = request.user.profile
    form = ProfileForm(instance=profile)
    staffs = Staff.objects.all()  # Fetch all staff members
    return render(request, 'demo/admin/staff_list.html', {'staffs': staffs, 'form': form})


# Admin Report
def report(request):
    flights = Flight_model.objects.all()
    staff_members = Staff.objects.all()
    admins = Admin.objects.all()

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
    writer.writerow(['First Name', 'Last Name', 'Origin', 'Destination',
                    'Travel Class', 'Departure Date', 'Return Date', 'Approved'])
    for flight in flights:
        writer.writerow([
            flight.user.first_name,
            flight.user.last_name,
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
    columns = ['First Name', 'Last Name', 'Origin', 'Destination',
               'Travel Class', 'Departure Date', 'Return Date', 'Approved']
    for col_num, column in enumerate(columns):
        ws.write(row, col_num, column)
    row += 1
    for flight in flights:
        ws.write(row, 0, flight.user.first_name)
        ws.write(row, 1, flight.user.last_name)
        ws.write(row, 2, flight.origin)
        ws.write(row, 3, flight.destination)
        ws.write(row, 4, flight.travel_class)
        ws.write(row, 5, flight.departure_date.strftime('%Y-%m-%d'))
        ws.write(row, 6, flight.return_date.strftime(
            '%Y-%m-%d') if flight.return_date else '')
        ws.write(row, 7, 'Approved' if flight.approved else 'Unapproved')
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
        messages.error(request, "PDF generation requires WeasyPrint native dependencies (gobject/pango). See README for setup or install the required runtime.")
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


def staff_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
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
        form = AuthenticationForm()

    return render(request, 'demo/auth/login.html', {'form': form})


def pending_flights(request):
    # Get the authenticated user
    user = request.user

    # Filter flights where `approved` is False and `user` is the authenticated user
    pending_flights = Flight_model.objects.filter(
        user=user, approved=False).order_by('-departure_date')
    return render(request, 'demo/staff/pending_flights.html', {'pending_flights': pending_flights})


def approved_flights(request):
    # Get the authenticated user
    user = request.user

    # Filter flights where `approved` is True and `user` is the authenticated user
    approved_flights = Flight_model.objects.filter(
        user=user, approved=True).order_by('-departure_date')

    return render(request, 'demo/staff/approved_flights.html', {'approved_flights': approved_flights})


# =========     PROFILE ===================>

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

    return render(request, 'demo/thrive_admin/update_price.html', {'increment_value': increment.increment_value})


def demo(request):
    user = request.user
    origin = request.POST.get("Origin")
    destination = request.POST.get("Destination")
    departure_date = request.POST.get("Departuredate")
    return_date = request.POST.get("Returndate")
    passenger_count = request.POST.get("passengerCount")

    kwargs = {
        "originLocationCode": origin,
        "destinationLocationCode": destination,
        "departureDate": departure_date,
        "adults": passenger_count,
    }

    tripPurpose = ""
    if return_date:
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
        except ResponseError as error:
            messages.error(
                request, error.response.result["errors"][0]["detail"])
            return render(request, "demo/home.html")

    if origin and destination and departure_date:
        try:
            search_flights = amadeus.shopping.flight_offers_search.get(
                **kwargs)
        except ResponseError as error:
            messages.error(
                request, error.response.result["errors"][0]["detail"])
            return render(request, "demo/home.html")

        search_flights_returned = []
        response = []

        for flight in search_flights.data:
            offer = Flight(flight).construct_flights()
            search_flights_returned.append(offer)

        response = zip(search_flights_returned, search_flights.data)
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
                logger.exception(f"Failed to parse flight data: json_err={json_err}, eval_err={eval_err}")
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
            Flight_model.objects.create(
                user=request.user,
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date if return_date else None,
                passenger_count=passenger_count,
                travel_class=travel_class,
                price=price_in_local_currency
            )

        print(f"Extracted flight details: departure_date={departure_date}, return_date={return_date}, "
              f"passenger_count={passenger_count}, travel_class={travel_class}, "
              f"origin={origin}, destination={destination}")

        # Find approved flights for any user matching the criteria
        approved_flights = Flight_model.objects.filter(
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
                user = approved_flight.user

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
                            passenger_name_record
                        )

                        # Render the success page
                        return render(request, "demo/book_flight.html", {"response": passenger_name_record})

                except Exception as booking_error:
                    logger.error(
                        f"Error booking flight for user {user.username}: {booking_error}")
                    messages.success(
                        request, f"Flight Booked {user.username}. Please check your mails.")
                    send_flight_email_2(user, origin, destination, departure_date,
                                        return_date)
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
                price=price_in_local_currency
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
    if request.is_ajax():
        try:
            data = amadeus.reference_data.locations.get(
                keyword=request.GET.get("term", None), subType=Location.ANY
            ).data
        except (ResponseError, KeyError, AttributeError) as error:
            messages.add_message(
                request, messages.ERROR, getattr(error, 'response', {}).get('result', {}).get('errors', [{'detail': str(error)}])[0]["detail"]
            )
            data = []
    return HttpResponse(get_city_airport_list(data), content_type="application/json")


def destination_airport_search(request):
    data = []
    if request.is_ajax():
        try:
            data = amadeus.reference_data.locations.get(
                keyword=request.GET.get("term", None), subType=Location.ANY
            ).data
        except (ResponseError, KeyError, AttributeError) as error:
            messages.add_message(
                request, messages.ERROR, getattr(error, 'response', {}).get('result', {}).get('errors', [{'detail': str(error)}])[0]["detail"]
            )
            data = []
    return HttpResponse(get_city_airport_list(data), content_type="application/json")


def get_city_airport_list(data):
    result = []
    for i, val in enumerate(data):
        result.append(data[i]["iataCode"] + ", " + data[i]["name"])
    result = list(dict.fromkeys(result))
    return json.dumps(result)


# ==========   ADMIN ============== >e
# Admin Registration View
def thrive_admin_register(request):
    if request.method == 'POST':
        form = ThriveAdminUserCreationForm(request.POST)
        if form.is_valid():
            # Save the user but don't commit yet
            user = form.save(commit=False)
            user.is_active = True  # Allow the user to login, but without admin privileges
            user.save()  # Now save the user

            # Create a Profile for the user
            Profile.objects.create(user=user)

            # Create the Admin profile with approval_status = False (unapproved)
            ThriveAdmin.objects.create(
                thrive_admin=user,
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
            return redirect('thrive_admin_login')
        else:
            messages.error(
                request, 'There was an error in the form. Please correct the errors.')
    else:
        form = ThriveAdminUserCreationForm()

    return render(request, 'demo/thrive_admin/admin_register.html', {'form': form})


def thrive_admin_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)

            if user is not None:
                try:
                    # Check if the user has an admin profile
                    admin_profile = ThriveAdmin.objects.get(admin=user)

                    if not admin_profile.approval_status:
                        messages.error(
                            request, 'Your account is awaiting approval from an existing admin.')
                        return render(request, 'demo/thrive_admin/admin_login.html', {'form': form})

                    # If approved, log in the admin
                    auth_login(request, user)
                    # messages.success(request, 'Thrive Admin login successful.')
                    return redirect('thrive_admin_approval_view')

                except ThriveAdmin.DoesNotExist:
                    messages.error(request, 'You do not have admin access.')
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()

    return render(request, 'demo/thrive_admin/admin_login.html', {'form': form})


def thrive_admin_approval_view(request):
    # Fetch all pending admins where approval_status is False
    pending_admins = ThriveAdmin.objects.filter(approval_status=False)

    if request.method == 'POST':
        admin_id = request.POST.get('admin_id')
        action = request.POST.get('action')

        # Fetch the admin by ID
        thrive_admin = get_object_or_404(ThriveAdmin, id=admin_id)

        if action == 'approve':
            thrive_admin.approval_status = True  # Approve the admin
            thrive_admin.save()
            messages.success(
                request, f'{thrive_admin.admin.username} has been approved as an admin.')
        elif action == 'disapprove':
            thrive_admin.approval_status = False  # Disapprove the admin
            thrive_admin.save()
            messages.error(
                request, f'{thrive_admin.admin.username} has been disapproved.')

        return redirect('thrive_admin_approval_view')

    return render(request, 'demo/thrive_admin/admin_approval.html', {'pending_admins': pending_admins})


# Admin Report
def thrive_report(request):
    flights = Flight_model.objects.all()
    staff_members = Staff.objects.all()
    admins = Admin.objects.all()

    # Handle Export to CSV, Excel, or PDF
    if 'export' in request.GET:
        file_format = request.GET.get('export')
        if file_format == 'csv':
            return export_combined_to_csv(flights, staff_members, admins)
        elif file_format == 'excel':
            return export_combined_to_excel(flights, staff_members, admins)
        elif file_format == 'pdf':
            return export_combined_to_pdf(request, flights, staff_members, admins)

    return render(request, 'demo/thrive_admin/report.html', {
        'flights': flights,
        'staff_members': staff_members,
        'admins': admins
    })


def send_flight_email(user, origin, destination, departure_date, return_date, passenger_name_record):
    # Get user profile details
    first_name = user.first_name
    last_name = user.last_name
    email = user.email
    phone = user.phone

    # Prepare the email subject and message
    subject = 'Flight Order From Online Booking Tool'
    message = render_to_string('demo/email/flight_booking_email.html', {
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'phone': phone,
        'origin': origin,
        'destination': destination,
        'departure_date': departure_date,
        'return_date': return_date,
        'response': passenger_name_record
    })

    # Create an EmailMessage instance
    email = EmailMessage(
        subject=subject,
        body=message,
        from_email=settings.EMAIL_HOST_USER,
        to=['david.edet@thrivenig.com'],  # Send to the user's email
    )

    # Optionally set headers or other properties
    email.content_subtype = 'html'  # If the message is HTML
    # email.attach('filename.txt', 'file content', 'text/plain')  # To attach files

    # Send email
    email.send(fail_silently=False)
    print("Email sent successfully!")


def send_flight_email_2(user, origin, destination, departure_date, return_date):
    # Get user profile details
    first_name = user.first_name
    last_name = user.last_name
    email = user.email
    phone = user.phone

    # Prepare the email subject and message
    subject = 'Flight Order From Online Booking Tool'
    message = render_to_string('demo/email/flight_booking_email.html', {
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'phone': phone,
        'origin': origin,
        'destination': destination,
        'departure_date': departure_date,
        'return_date': return_date

    })

    # Create an EmailMessage instance
    email = EmailMessage(
        subject=subject,
        body=message,
        from_email=settings.EMAIL_HOST_USER,
        to=['david.edet@thrivenig.com'],  # Send to the user's email
    )

    # Optionally set headers or other properties
    email.content_subtype = 'html'  # If the message is HTML
    # email.attach('filename.txt', 'file content', 'text/plain')  # To attach files

    # Send email
    email.send(fail_silently=False)
    print("Email sent successfully!")


def send_flight_pending_email(user, origin, destination, departure_date, return_date, passenger_count, price):
    subject = "Flight Approval Pending"
    from_email = settings.EMAIL_HOST_USER
    to_email = ['david.edet@thrivenig.com']

    # Render the HTML template and strip it to plain text
    html_content = render_to_string("demo/email/flight_pending_email.html", {
        "user": user,
        "origin": origin,
        "destination": destination,
        "departure_date": departure_date,
        "return_date": return_date,
        "passenger_count": passenger_count,
        "price": price
    })
    text_content = strip_tags(html_content)

    # Create the email object
    email = EmailMultiAlternatives(subject, text_content, from_email, to_email)
    email.attach_alternative(html_content, "text/html")

    # Send the email
    email.send(fail_silently=False)
    print("Email sent successfully!")


# ===========  HOTEL ===============>



def hotel(request):
    origin = request.POST.get('Origin')
    checkinDate = request.POST.get('Checkindate')
    checkoutDate = request.POST.get('Checkoutdate')

    guest_count = request.POST.get('guestCount', '1')  # Default to 1 if not provided
    kwargs = {'cityCode': request.POST.get('Origin'),
              'checkInDate': request.POST.get('Checkindate'),
              'checkOutDate': request.POST.get('Checkoutdate'),
              'adults': int(guest_count)}  # Add guest count to the search parameters

    if origin and checkinDate and checkoutDate:
        # Store guest count in session for later use during booking
        request.session['guest_count'] = int(guest_count)
        
        try:
            # Hotel List
            hotel_list = amadeus.reference_data.locations.hotels.by_city.get(
                cityCode=origin)
        except ResponseError as error:
            messages.add_message(request, messages.ERROR, error.response.body)
            return render(request, 'demo/hotel/demo_form.html', {})
        hotel_offers = []
        hotel_ids = []
        for i in hotel_list.data:
            hotel_ids.append(i['hotelId'])
        num_hotels = 40
        kwargs = {'hotelIds': hotel_ids[0:num_hotels],
                  'checkInDate': request.POST.get('Checkindate'),
                  'checkOutDate': request.POST.get('Checkoutdate'),
                  'adults': int(guest_count)}
        try:
            # Hotel Search
            search_hotels = amadeus.shopping.hotel_offers_search.get(**kwargs)
        except ResponseError as error:
            messages.add_message(request, messages.ERROR, error.response.body)
            return render(request, 'demo/hotel/demo_form.html', {})
        try:
            for hotel in search_hotels.data:
                offer = Hotel(hotel).construct_hotel()
                hotel_offers.append(offer)
                response = zip(hotel_offers, search_hotels.data)

            return render(request, 'demo/hotel/results.html', {'response': response,
                                                               'origin': origin,
                                                               'departureDate': checkinDate,
                                                               'returnDate': checkoutDate,
                                                               })
        except UnboundLocalError:
            messages.add_message(request, messages.ERROR, 'No hotels found.')
            return render(request, 'demo/hotel/demo_form.html', {})
    return render(request, 'demo/hotel/demo_form.html', {})


def rooms_per_hotel(request, hotel, departureDate, returnDate):
    try:
        # Search for rooms in a given hotel
        rooms = amadeus.shopping.hotel_offers_search.get(hotelIds=hotel,
                                                         checkInDate=departureDate,
                                                         checkOutDate=returnDate).data
        hotel_rooms = Room(rooms).construct_room()
        return render(request, 'demo/hotel/rooms_per_hotel.html', {'response': hotel_rooms,
                                                                   'name': rooms[0]['hotel']['name'],
                                                                   })
    except (TypeError, AttributeError, ResponseError, KeyError) as error:
        messages.add_message(request, messages.ERROR, error)
        return render(request, 'demo/hotel/rooms_per_hotel.html', {})


# def book_hotel(request, offer_id):
#     try:
#         # Confirm availability of a given offer
#         offer_availability = amadeus.shopping.hotel_offer_search(
#             offer_id).get()
#         if offer_availability.status_code == 200:
#             guests = [{'id': 1, 'name': {'title': 'MR', 'firstName': 'BOB', 'lastName': 'SMITH'},
#                        'contact': {'phone': '+33679278416', 'email': 'bob.smith@email.com'}}]

#             payments = {'id': 1, 'method': 'creditCard',
#                         'card': {'vendorCode': 'VI', 'cardNumber': '4151289722471370', 'expiryDate': '2027-08'}}
#             booking = amadeus.booking.hotel_bookings.post(
#                 offer_id, guests, payments).data
#         else:
#             return render(request, 'demo/hotel/booking.html', {'response': 'The room is not available'})
#     except ResponseError as error:
#         messages.add_message(request, messages.ERROR, error.response.body)
#         return render(request, 'demo/hotel/booking.html', {})
#     return render(request, 'demo/hotel/booking.html', {'id': booking[0]['id'],
#                                                        'providerConfirmationId': booking[0]['providerConfirmationId']
#                                                        })


def send_hotel_booking_email(user, hotel_details, booking_details):
    subject = "Hotel Booking Confirmation from Online Booking Tool"
    from_email = settings.EMAIL_HOST_USER
    to_email = ['david.edet@thrivenig.com']  # Replace with actual email

    # Render the HTML template and strip it to plain text
    html_content = render_to_string("demo/email/hotel_booking_email.html", {
        "user": user,
        "hotel_name": hotel_details['hotel']['name'],
        "check_in_date": hotel_details['offers'][0]['checkInDate'],
        "check_out_date": hotel_details['offers'][0]['checkOutDate'],
        "room_type": hotel_details['offers'][0]['room']['type'],
        "booking_id": booking_details[0]['id'],
        "confirmation_id": booking_details[0]['providerConfirmationId'],
        "total_price": hotel_details['offers'][0]['price']['total'],
        "currency": hotel_details['offers'][0]['price']['currency']
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

def book_hotel(request, offer_id):
    try:
        # Get the guest count from the session or use default
        guest_count = request.session.get('guest_count', 1)
        
        # Confirm availability of a given offer
        offer_availability = amadeus.shopping.hotel_offer_search(offer_id).get()

        if offer_availability.status_code == 200:
            # Create a list of guest entries based on the guest count
            guests = [{
                'id': 1,
                'name': {
                    'title': 'MR',
                    'firstName': 'BOB',
                    'lastName': 'SMITH'
                },
                'contact': {
                    'phone': '+33679278416',
                    'email': 'bob.smith@email.com'
                }
            }]

            payments = {
                'id': 1,
                'method': 'creditCard',
                'card': {
                    'vendorCode': 'VI',
                    'cardNumber': '4151289722471370',
                    'expiryDate': '2027-08'
                }
            }

            booking = amadeus.booking.hotel_bookings.post(offer_id, guests, payments).data

            # Send confirmation email
            send_hotel_booking_email(
                user=request.user,
                hotel_details=offer_availability.data[0],
                booking_details=booking
            )

            return render(request, 'demo/hotel/booking.html', {
                'id': booking[0]['id'],
                'providerConfirmationId': booking[0]['providerConfirmationId']
            })
        else:
            return render(request, 'demo/hotel/booking.html', {
                'response': 'The room is not available'
            })

    except ResponseError as error:
        messages.add_message(request, messages.ERROR, error.response.body)
        return render(request, 'demo/hotel/booking.html', {})



def city_search(request):
    if request.is_ajax():
        try:
            data = amadeus.reference_data.locations.get(keyword=request.GET.get('term', None),
                                                        subType=Location.ANY).data
        except ResponseError as error:
            messages.add_message(request, messages.ERROR, error.response.body)
    return HttpResponse(get_city_list(data), 'application/json')




def get_city_list(data):
    result = []
    for i, val in enumerate(data):
        result.append(data[i]['iataCode'] + ', ' + data[i]['name'])
    result = list(dict.fromkeys(result))
    return json.dumps(result)
