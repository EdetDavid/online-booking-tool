from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from datetime import date
from unittest.mock import patch

import json
import requests
from django.core import mail
from django.core.mail import EmailMultiAlternatives, send_mail
from django.test import override_settings
from . import views
from .local_flights import local_multi_city_search
from .models import Admin, Flight_model, Organization, Profile, Staff, TravelAgency


class BookingCartTests(TestCase):
    def setUp(self):
        self.flight_data = {
            "id": "CART-FLIGHT-1",
            "source": "LOCAL_FLIGHT_FARE",
            "price": {"currency": "USD", "total": "500.00"},
            "numberOfBookableSeats": 7,
            "itineraries": [
                {
                    "duration": "PT6H",
                    "segments": [
                        {
                            "departure": {
                                "iataCode": "LOS",
                                "at": "2026-07-10T09:00:00",
                            },
                            "arrival": {
                                "iataCode": "JFK",
                                "at": "2026-07-10T15:00:00",
                            },
                            "carrierCode": "B6",
                            "duration": "PT6H",
                        }
                    ],
                }
            ],
            "travelerPricings": [
                {
                    "fareDetailsBySegment": [
                        {"segmentId": "1", "cabin": "ECONOMY"}
                    ]
                }
            ],
        }

    def test_cart_stores_flights_hotels_and_blocks_duplicates(self):
        flight_response = self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )
        self.assertRedirects(flight_response, reverse("cart_detail"))

        self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )
        hotel_response = self.client.post(
            reverse("cart_add_hotel"),
            {
                "offer_id": "LOCAL-HOTEL-LOS-1-ROOM-1-20260710-20260712-G1",
                "hotel_name": "Harbour View Hotel",
                "description": "Executive room",
                "check_in": "2026-07-10",
                "check_out": "2026-07-12",
                "guests": "1",
                "price": "250,000",
            },
        )
        self.assertRedirects(hotel_response, reverse("cart_detail"))

        items = self.client.session["booking_cart"]["items"]
        self.assertEqual(len(items), 2)
        response = self.client.get(reverse("cart_detail"))
        self.assertContains(response, "LOS to JFK")
        self.assertContains(response, "Harbour View Hotel")
        self.assertContains(response, "1,050,000")

    def test_cart_item_can_be_removed_and_cart_cleared(self):
        self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )
        item_id = self.client.session["booking_cart"]["items"][0]["id"]

        self.client.post(reverse("cart_remove", args=[item_id]))
        self.assertEqual(self.client.session["booking_cart"]["items"], [])

        self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )
        self.client.post(reverse("cart_clear"))
        self.assertEqual(self.client.session["booking_cart"]["items"], [])

    @patch("demo.views.send_flight_pending_email")
    def test_submitting_cart_flight_creates_request_and_removes_item(
        self,
        mock_pending_email,
    ):
        user = get_user_model().objects.create_user(
            username="cart_staff",
            email="cart-staff@example.com",
            password="password-123",
        )
        organization = Organization.objects.create(
            name="Cart Organization",
            join_code="CARTORG",
        )
        Staff.objects.create(
            staff=user,
            organization=organization,
            first_name="Cart",
            last_name="Staff",
        )
        Profile.objects.create(user=user)

        self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )
        item_id = self.client.session["booking_cart"]["items"][0]["id"]
        self.client.force_login(user)

        response = self.client.post(
            reverse("book_flight"),
            {"cart_item_id": item_id},
        )

        self.assertRedirects(response, reverse("home"))
        self.assertTrue(
            Flight_model.objects.filter(
                user=user,
                origin="LOS",
                destination="JFK",
                approved=False,
            ).exists()
        )
        self.assertEqual(self.client.session["booking_cart"]["items"], [])
        mock_pending_email.assert_called_once()


@override_settings(USE_LIVE_FLIGHT_API=False)
class FlightSearchTripTypeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="search_staff",
            email="search-staff@example.com",
            password="password-123",
        )
        self.organization = Organization.objects.create(
            name="Search Organization",
            join_code="SEARCHORG",
        )
        Staff.objects.create(
            staff=self.user,
            organization=self.organization,
            first_name="Search",
            last_name="Staff",
        )
        Profile.objects.create(user=self.user)
        self.client.force_login(self.user)

    def test_one_way_search_returns_single_leg_itineraries(self):
        response = self.client.post(
            reverse("home"),
            {
                "tripType": "one-way",
                "Origin": "LOS",
                "Destination": "JFK",
                "Departuredate": "2026-07-10",
                "Returndate": "2026-07-18",
                "passengerCount": "1",
                "cabinClassTop": "economy",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-trip-type="one-way"', count=18)
        self.assertNotContains(response, '<div class="leg-label">Return</div>')

    def test_round_trip_search_returns_outbound_and_return_legs(self):
        response = self.client.post(
            reverse("home"),
            {
                "tripType": "round-trip",
                "Origin": "LOS",
                "Destination": "JFK",
                "Departuredate": "2026-07-10",
                "Returndate": "2026-07-18",
                "passengerCount": "2",
                "cabinClassTop": "business",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-trip-type="round-trip"', count=18)
        self.assertContains(response, '<div class="leg-label">Return</div>')

    def test_multi_city_search_returns_every_requested_leg(self):
        response = self.client.post(
            reverse("home"),
            {
                "tripType": "multi-city",
                "multi_origin": ["LOS", "ACC", "LHR"],
                "multi_destination": ["ACC", "LHR", "JFK"],
                "multi_date": ["2026-07-10", "2026-07-14", "2026-07-20"],
                "passengerCount": "1",
                "cabinClassTop": "economy",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Multi-city trip")
        self.assertContains(response, '<div class="leg-label">Flight 3</div>')
        self.assertContains(response, 'data-trip-type="multi-city"', count=18)

    def test_multi_city_rejects_dates_out_of_order(self):
        response = self.client.post(
            reverse("home"),
            {
                "tripType": "multi-city",
                "multi_origin": ["LOS", "ACC"],
                "multi_destination": ["ACC", "LHR"],
                "multi_date": ["2026-07-20", "2026-07-14"],
                "passengerCount": "1",
                "cabinClassTop": "economy",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "flight dates must be in chronological order.",
        )
        self.assertNotContains(response, "flight-result-card")

    @patch("demo.views.send_flight_pending_email")
    def test_multi_city_booking_uses_final_destination_and_trip_end_date(
        self,
        mock_pending_email,
    ):
        offer = local_multi_city_search(
            [
                {
                    "origin": "LOS",
                    "destination": "ACC",
                    "departure_date": "2026-07-10",
                },
                {
                    "origin": "ACC",
                    "destination": "LHR",
                    "departure_date": "2026-07-14",
                },
                {
                    "origin": "LHR",
                    "destination": "JFK",
                    "departure_date": "2026-07-20",
                },
            ],
            passenger_count=1,
            cabin="ECONOMY",
            max_offers=1,
        )[0]

        response = self.client.post(
            reverse("book_flight"),
            {"flight_data": json.dumps(offer)},
        )

        self.assertRedirects(response, reverse("home"))
        request = Flight_model.objects.get(user=self.user)
        self.assertEqual(request.origin, "LOS")
        self.assertEqual(request.destination, "JFK")
        self.assertEqual(request.return_date.isoformat(), "2026-07-20")
        mock_pending_email.assert_called_once()


@override_settings(USE_LIVE_HOTEL_API=False)
class HotelJourneyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="hotel_staff",
            email="hotel-staff@example.com",
            password="password-123",
        )
        self.organization = Organization.objects.create(
            name="Hotel Organization",
            join_code="HOTELORG",
        )
        Staff.objects.create(
            staff=self.user,
            organization=self.organization,
            first_name="Hotel",
            last_name="Staff",
        )
        Profile.objects.create(user=self.user)

    def test_hotel_search_validates_checkout_after_checkin(self):
        response = self.client.post(
            reverse("hotel"),
            {
                "Origin": "LOS",
                "Checkindate": "2026-07-12",
                "Checkoutdate": "2026-07-10",
                "guestCount": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check-out must be after check-in.")
        self.assertNotContains(response, "stay-result-card")

    def test_hotel_search_returns_results_and_preserves_guest_count(self):
        response = self.client.post(
            reverse("hotel"),
            {
                "Origin": "LOS",
                "Checkindate": "2026-07-10",
                "Checkoutdate": "2026-07-12",
                "guestCount": "2",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "stay-result-card", count=12)
        self.assertContains(response, "2 guests")
        self.assertEqual(self.client.session["guest_count"], 2)

    def test_local_room_page_shows_room_choices_and_total_stay_facts(self):
        session = self.client.session
        session["guest_count"] = 2
        session.save()

        response = self.client.get(
            reverse(
                "rooms_per_hotel",
                args=["LOCAL-HOTEL-LOS-1", "2026-07-10", "2026-07-12"],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "room-result-card", count=3)
        self.assertContains(response, "2 nights")
        self.assertContains(response, "2 guests")

    @patch("demo.views.send_hotel_booking_email")
    def test_local_room_booking_generates_confirmation_email(
        self,
        mock_send_email,
    ):
        self.client.force_login(self.user)
        offer_id = "LOCAL-HOTEL-LOS-1-ROOM-1-20260710-20260712-G1"

        response = self.client.post(
            reverse("book_hotel", args=[offer_id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hotel Booking Successful")
        mock_send_email.assert_called_once()
        hotel_details, booking_details = mock_send_email.call_args.args[1:]
        self.assertEqual(hotel_details["offers"][0]["id"], offer_id)
        self.assertTrue(booking_details[0]["providerConfirmationId"])

    def test_hotel_booking_requires_staff_login(self):
        response = self.client.post(
            reverse(
                "book_hotel",
                args=["LOCAL-HOTEL-LOS-1-ROOM-1-20260710-20260712-G1"],
            )
        )

        self.assertRedirects(
            response,
            reverse("login") + "?next=" + reverse(
                "book_hotel",
                args=["LOCAL-HOTEL-LOS-1-ROOM-1-20260710-20260712-G1"],
            ),
        )


class TravelAgencyLoginTests(TestCase):
    def setUp(self):
        self.password = "strong-test-password-123"
        self.user = get_user_model().objects.create_user(
            username="agency_user",
            email="agency@example.com",
            password=self.password,
        )
        self.agency = TravelAgency.objects.create(
            admin=self.user,
            first_name="Agency",
            last_name="User",
            company_code="agency123",
            approval_status=True,
        )
        self.url = reverse("travel_agency_login")

    def test_company_code_is_required_for_travel_agency_login(self):
        response = self.client.post(
            self.url,
            {
                "username": self.user.username,
                "password": self.password,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_travel_agency_login_rejects_wrong_company_code(self):
        response = self.client.post(
            self.url,
            {
                "username": self.user.username,
                "company_code": "WRONG123",
                "password": self.password,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid company code.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_travel_agency_login_accepts_matching_company_code(self):
        response = self.client.post(
            self.url,
            {
                "username": self.user.username,
                "company_code": "agency123",
                "password": self.password,
            },
        )

        self.assertRedirects(
            response,
            reverse("travel_agency_approval_view"),
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))


class CsrfFailureTests(TestCase):
    def test_missing_login_csrf_redirects_with_toast_message(self):
        csrf_client = Client(enforce_csrf_checks=True)
        login_url = reverse("login")

        response = csrf_client.post(
            login_url,
            {
                "username": "anyone",
                "password": "password",
            },
            HTTP_REFERER=f"http://testserver{login_url}",
            follow=True,
        )

        self.assertRedirects(response, f"http://testserver{login_url}")
        self.assertContains(response, "Your session expired. Please refresh the page and try again.")
        self.assertContains(response, "app-toast")


class BrevoEmailBackendTests(TestCase):
    @override_settings(
        EMAIL_BACKEND="demo.brevo_email_backend.BrevoEmailBackend",
        BREVO_API_KEY="test-api-key",
        BREVO_API_URL="https://api.brevo.com/v3/smtp/email",
        BREVO_SENDER_EMAIL="bookings@example.com",
        BREVO_SENDER_NAME="Online Booking Tool",
    )
    @patch("demo.brevo_email_backend.requests.post")
    def test_brevo_backend_sends_plain_email_payload(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None

        sent_count = send_mail(
            "Booking received",
            "Your request is pending approval.",
            "ignored@example.com",
            ["traveler@example.com"],
        )

        self.assertEqual(sent_count, 1)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["sender"]["email"], "bookings@example.com")
        self.assertEqual(payload["sender"]["name"], "Online Booking Tool")
        self.assertEqual(payload["to"], [{"email": "traveler@example.com"}])
        self.assertEqual(payload["subject"], "Booking received")
        self.assertIn("Your request is pending approval.", payload["htmlContent"])
        self.assertEqual(
            mock_post.call_args.kwargs["headers"]["api-key"],
            "test-api-key",
        )

    @override_settings(
        EMAIL_BACKEND="demo.brevo_email_backend.BrevoEmailBackend",
        BREVO_API_KEY="test-api-key",
        BREVO_SENDER_EMAIL="bookings@example.com",
        BREVO_SENDER_NAME="Online Booking Tool",
    )
    @patch("demo.brevo_email_backend.requests.post")
    def test_brevo_backend_prefers_html_alternative(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        message = EmailMultiAlternatives(
            "Booking approved",
            "Plain body",
            "ignored@example.com",
            ["traveler@example.com"],
        )
        message.attach_alternative("<strong>Approved</strong>", "text/html")

        sent_count = message.send()

        self.assertEqual(sent_count, 1)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["htmlContent"], "<strong>Approved</strong>")
        self.assertEqual(payload["textContent"], "Plain body")

    @override_settings(
        EMAIL_BACKEND="demo.brevo_email_backend.BrevoEmailBackend",
        EMAIL_FALLBACK_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        BREVO_API_KEY="test-api-key",
        BREVO_SENDER_EMAIL="bookings@example.com",
        BREVO_SENDER_NAME="Online Booking Tool",
    )
    @patch("demo.brevo_email_backend.requests.post")
    def test_brevo_backend_uses_fallback_after_http_rejection(self, mock_post):
        response = requests.Response()
        response.status_code = 401
        response.url = "https://api.brevo.com/v3/smtp/email"
        mock_post.return_value = response

        sent_count = send_mail(
            "Approval required",
            "A flight request needs approval.",
            "verified@example.com",
            ["admin@example.com"],
        )

        self.assertEqual(sent_count, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Approval required")


class TravelAgencyFlightMappingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.agency_user = User.objects.create_user(
            username="managed_agency",
            email="managed-agency@example.com",
            password="password-123",
        )
        self.other_agency_user = User.objects.create_user(
            username="other_agency",
            email="other-agency@example.com",
            password="password-123",
        )
        self.agency = TravelAgency.objects.create(
            admin=self.agency_user,
            first_name="Managed",
            last_name="Agency",
            company_code="MANAGED123",
            approval_status=True,
        )
        self.other_agency = TravelAgency.objects.create(
            admin=self.other_agency_user,
            first_name="Other",
            last_name="Agency",
            company_code="OTHER123",
            approval_status=True,
        )
        self.organization_a = Organization.objects.create(
            name="Corporate One",
            travel_agency=self.agency,
        )
        self.organization_b = Organization.objects.create(
            name="Corporate Two",
            travel_agency=self.agency,
        )
        self.other_organization = Organization.objects.create(
            name="Other Corporate",
            travel_agency=self.other_agency,
        )
        staff_user = User.objects.create_user(
            username="corp_staff",
            email="corp-staff@example.com",
            password="password-123",
        )
        self.staff = Staff.objects.create(
            staff=staff_user,
            organization=self.organization_a,
            first_name="Corp",
            last_name="Staff",
        )
        admin_user = User.objects.create_user(
            username="corp_admin",
            email="corp-admin@example.com",
            password="password-123",
        )
        self.admin = Admin.objects.create(
            admin=admin_user,
            organization=self.organization_b,
            first_name="Corp",
            last_name="Admin",
            approval_status=True,
        )
        org_a_admin_user = User.objects.create_user(
            username="corp_one_admin",
            email="corp-one-admin@example.com",
            password="password-123",
        )
        self.org_a_admin = Admin.objects.create(
            admin=org_a_admin_user,
            organization=self.organization_a,
            first_name="Corp",
            last_name="One Admin",
            approval_status=True,
        )
        self.managed_flight = self.create_flight(
            self.organization_a,
            travel_agency=self.agency,
            origin="LOS",
        )
        self.fallback_mapped_flight = self.create_flight(
            self.organization_b,
            travel_agency=None,
            origin="ABV",
        )
        self.other_flight = self.create_flight(
            self.other_organization,
            travel_agency=self.other_agency,
            origin="PHC",
        )

    def create_flight(self, organization, travel_agency, origin):
        return Flight_model.objects.create(
            user=self.agency_user,
            organization=organization,
            travel_agency=travel_agency,
            origin=origin,
            destination="DXB",
            departure_date=date(2026, 7, 1),
            passenger_count=1,
            travel_class="ECONOMY",
            price=1000,
        )

    def test_flight_can_resolve_agent_from_direct_or_organization_mapping(self):
        self.assertEqual(self.managed_flight.mapped_travel_agency(), self.agency)
        self.assertEqual(self.fallback_mapped_flight.mapped_travel_agency(), self.agency)

    def test_travel_agency_report_is_scoped_to_managed_organizations(self):
        self.client.force_login(self.agency_user)

        response = self.client.get(reverse("travel_agency_report"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.managed_flight, response.context["flights"])
        self.assertIn(self.fallback_mapped_flight, response.context["flights"])
        self.assertNotIn(self.other_flight, response.context["flights"])
        self.assertIn(self.staff, response.context["staff_members"])
        self.assertIn(self.admin, response.context["admins"])

    def test_travel_agency_approved_flights_are_scoped_to_approved_managed_requests(self):
        self.managed_flight.approved = True
        self.managed_flight.save(update_fields=["approved"])
        self.fallback_mapped_flight.approved = True
        self.fallback_mapped_flight.save(update_fields=["approved"])
        self.other_flight.approved = True
        self.other_flight.save(update_fields=["approved"])
        unapproved_flight = self.create_flight(
            self.organization_a,
            travel_agency=self.agency,
            origin="ENU",
        )
        self.client.force_login(self.agency_user)

        response = self.client.get(reverse("travel_agency_approved_flights"))

        self.assertEqual(response.status_code, 200)
        approved_flights = list(response.context["approved_flights"])
        self.assertIn(self.managed_flight, approved_flights)
        self.assertIn(self.fallback_mapped_flight, approved_flights)
        self.assertNotIn(self.other_flight, approved_flights)
        self.assertNotIn(unapproved_flight, approved_flights)

    @patch("demo.views.send_html_email")
    def test_approving_flight_emails_requesting_staff_and_mapped_agency(self, mock_send_email):
        flight = Flight_model.objects.create(
            user=self.staff.staff,
            requested_by_staff=self.staff,
            organization=self.organization_a,
            travel_agency=None,
            assigned_admin=self.org_a_admin,
            origin="LOS",
            destination="LHR",
            departure_date=date(2026, 8, 3),
            passenger_count=1,
            travel_class="BUSINESS",
            price=2500,
        )
        self.client.force_login(self.org_a_admin.admin)

        response = self.client.post(
            reverse("approve_flight"),
            {"flight_ids": [str(flight.id)]},
        )

        self.assertRedirects(response, reverse("approve_flight"))
        flight.refresh_from_db()
        self.assertTrue(flight.approved)
        mock_send_email.assert_called_once()
        self.assertEqual(
            mock_send_email.call_args.args[3],
            ["corp-staff@example.com", "managed-agency@example.com"],
        )

    def test_flight_admin_recipients_use_connected_organization_admins(self):
        self.assertEqual(
            views.flight_admin_recipients(self.managed_flight),
            ["corp-one-admin@example.com"],
        )


class CorporateOrganizationOnboardingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.agency_user = User.objects.create_user(
            username="agency_owner",
            email="agency-owner@example.com",
            password="password-123",
        )
        self.agency = TravelAgency.objects.create(
            admin=self.agency_user,
            first_name="Agency",
            last_name="Owner",
            company_code="OWNER123",
            approval_status=True,
        )

    def test_travel_agency_can_create_corporate_organization_with_join_code(self):
        self.client.force_login(self.agency_user)

        response = self.client.post(
            reverse("travel_agency_organizations"),
            {
                "name": "Acme Limited",
                "join_code": " acme 123 ",
            },
        )

        self.assertRedirects(response, reverse("travel_agency_organizations"))
        organization = Organization.objects.get(name="Acme Limited")
        self.assertEqual(organization.travel_agency, self.agency)
        self.assertEqual(organization.join_code, "ACME123")
        self.assertTrue(organization.active)

    def test_travel_agency_can_update_managed_organization(self):
        organization = Organization.objects.create(
            name="Old Client",
            join_code="OLDCLIENT",
            travel_agency=self.agency,
        )
        self.client.force_login(self.agency_user)

        response = self.client.post(
            reverse("travel_agency_organizations"),
            {
                "organization_id": organization.id,
                "action": "update",
                "name": "New Client",
                "join_code": " new client ",
            },
        )

        self.assertRedirects(response, reverse("travel_agency_organizations"))
        organization.refresh_from_db()
        self.assertEqual(organization.name, "New Client")
        self.assertEqual(organization.join_code, "NEWCLIENT")

    def test_travel_agency_can_claim_existing_unassigned_organization(self):
        organization = Organization.objects.create(
            name="Unassigned Client",
            join_code="UNASSIGNED",
        )
        flight = Flight_model.objects.create(
            user=self.agency_user,
            organization=organization,
            origin="LOS",
            destination="ABV",
            departure_date=date(2026, 8, 1),
            passenger_count=1,
            travel_class="ECONOMY",
            price=1000,
        )
        self.client.force_login(self.agency_user)

        response = self.client.post(
            reverse("travel_agency_organizations"),
            {
                "organization_id": organization.id,
                "action": "claim",
            },
        )

        self.assertRedirects(response, reverse("travel_agency_organizations"))
        organization.refresh_from_db()
        flight.refresh_from_db()
        self.assertEqual(organization.travel_agency, self.agency)
        self.assertEqual(flight.travel_agency, self.agency)

    def test_travel_agency_cannot_claim_another_agencys_organization(self):
        User = get_user_model()
        other_agency_user = User.objects.create_user(
            username="other_owner",
            email="other-owner@example.com",
            password="password-123",
        )
        other_agency = TravelAgency.objects.create(
            admin=other_agency_user,
            first_name="Other",
            last_name="Owner",
            company_code="OTHEROWNER",
            approval_status=True,
        )
        organization = Organization.objects.create(
            name="Taken Client",
            join_code="TAKEN",
            travel_agency=other_agency,
        )
        self.client.force_login(self.agency_user)

        response = self.client.post(
            reverse("travel_agency_organizations"),
            {
                "organization_id": organization.id,
                "action": "claim",
            },
        )

        self.assertEqual(response.status_code, 404)
        organization.refresh_from_db()
        self.assertEqual(organization.travel_agency, other_agency)

    def test_staff_registers_with_valid_organization_code(self):
        organization = Organization.objects.create(
            name="Acme Limited",
            join_code="ACME123",
            travel_agency=self.agency,
        )

        response = self.client.post(
            reverse("register"),
            {
                "username": "acme_staff",
                "first_name": "Acme",
                "last_name": "Staff",
                "email": "acme-staff@example.com",
                "phone": "",
                "organization_code": " acme123 ",
                "password1": "complex-password-123",
                "password2": "complex-password-123",
            },
        )

        self.assertRedirects(response, reverse("profile"))
        staff = Staff.objects.get(staff__username="acme_staff")
        self.assertEqual(staff.organization, organization)

    def test_staff_registration_rejects_invalid_organization_code(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "unknown_staff",
                "first_name": "Unknown",
                "last_name": "Staff",
                "email": "unknown-staff@example.com",
                "phone": "",
                "organization_code": "missing",
                "password1": "complex-password-123",
                "password2": "complex-password-123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid organization code.")
        self.assertFalse(Staff.objects.filter(staff__username="unknown_staff").exists())


class RoleGuardTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.organization = Organization.objects.create(
            name="Guard Corp",
            join_code="GUARD",
        )
        self.staff_user = User.objects.create_user(
            username="guard_staff",
            email="guard-staff@example.com",
            password="password-123",
        )
        self.staff = Staff.objects.create(
            staff=self.staff_user,
            organization=self.organization,
            first_name="Guard",
            last_name="Staff",
        )
        Profile.objects.create(user=self.staff_user)
        self.admin_user = User.objects.create_user(
            username="guard_admin",
            email="guard-admin@example.com",
            password="password-123",
        )
        self.admin = Admin.objects.create(
            admin=self.admin_user,
            organization=self.organization,
            first_name="Guard",
            last_name="Admin",
            approval_status=True,
        )
        Profile.objects.create(user=self.admin_user)
        self.agency_user = User.objects.create_user(
            username="guard_agency",
            email="guard-agency@example.com",
            password="password-123",
        )
        self.agency = TravelAgency.objects.create(
            admin=self.agency_user,
            first_name="Guard",
            last_name="Agency",
            company_code="GUARDAGENCY",
            approval_status=True,
        )
        Profile.objects.create(user=self.agency_user)

    def test_staff_cannot_access_admin_or_agency_pages(self):
        self.client.force_login(self.staff_user)

        admin_response = self.client.get(reverse("admin_profile"))
        agency_response = self.client.get(reverse("travel_agency_organizations"))

        self.assertRedirects(admin_response, reverse("profile"))
        self.assertRedirects(agency_response, reverse("profile"))

    def test_admin_cannot_access_staff_or_agency_pages(self):
        self.client.force_login(self.admin_user)

        staff_response = self.client.get(reverse("profile"))
        agency_response = self.client.get(reverse("travel_agency_organizations"))

        self.assertRedirects(staff_response, reverse("admin_profile"))
        self.assertRedirects(agency_response, reverse("admin_profile"))

    def test_agency_cannot_access_staff_or_admin_pages(self):
        self.client.force_login(self.agency_user)

        staff_response = self.client.get(reverse("profile"))
        admin_response = self.client.get(reverse("admin_profile"))

        self.assertRedirects(staff_response, reverse("travel_agency_organizations"))
        self.assertRedirects(admin_response, reverse("travel_agency_organizations"))

    def test_book_flight_requires_staff_role(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(reverse("book_flight"), {"flight_data": "{}"})

        self.assertRedirects(response, reverse("admin_profile"))
