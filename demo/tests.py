from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from datetime import date
from unittest.mock import patch

import requests
from django.core import mail
from django.core.mail import EmailMultiAlternatives, send_mail
from django.test import override_settings
from . import views
from .models import Admin, Flight_model, Organization, Profile, Staff, TravelAgency


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
