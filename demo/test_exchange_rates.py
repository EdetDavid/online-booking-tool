import json
from datetime import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .booking import Booking
from .flight import flight_price_naira
from .hotel import format_price_naira, price_value_naira
from .local_flights import build_local_offer, local_booking_confirmation
from .local_hotels import local_hotel_offer
from .models import (
    Flight_model,
    Organization,
    PriceIncrement,
    Staff,
    TravelAgency,
)
from .pricing import DEFAULT_EXCHANGE_RATE, exchange_rate_for_user


class ExchangeRateDashboardTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.agency_user = user_model.objects.create_user(
            username="rate_agency",
            email="rate-agency@example.com",
            password="password-123",
        )
        self.agency = TravelAgency.objects.create(
            admin=self.agency_user,
            company_code="RATEAGENCY",
            approval_status=True,
        )
        self.other_agency_user = user_model.objects.create_user(
            username="other_rate_agency",
            email="other-rate-agency@example.com",
            password="password-123",
        )
        self.other_agency = TravelAgency.objects.create(
            admin=self.other_agency_user,
            company_code="OTHERRATE",
            approval_status=True,
            exchange_rate=Decimal("1725.0000"),
        )

    def test_approved_agency_can_update_only_its_exchange_rate(self):
        self.client.force_login(self.agency_user)

        response = self.client.post(
            reverse("update_exchange_rate"),
            {"exchange_rate": "1525.7500"},
        )

        self.assertRedirects(response, reverse("update_exchange_rate"))
        self.agency.refresh_from_db()
        self.other_agency.refresh_from_db()
        self.assertEqual(self.agency.exchange_rate, Decimal("1525.7500"))
        self.assertEqual(self.other_agency.exchange_rate, Decimal("1725.0000"))

    def test_invalid_exchange_rates_are_rejected(self):
        self.client.force_login(self.agency_user)

        for invalid_rate in ("0", "-1", "not-a-number", "NaN", "Infinity"):
            with self.subTest(exchange_rate=invalid_rate):
                response = self.client.post(
                    reverse("update_exchange_rate"),
                    {"exchange_rate": invalid_rate},
                )
                self.assertEqual(response.status_code, 200)
                self.agency.refresh_from_db()
                self.assertEqual(self.agency.exchange_rate, DEFAULT_EXCHANGE_RATE)

    def test_unapproved_agency_cannot_open_exchange_rate_dashboard(self):
        self.agency.approval_status = False
        self.agency.save(update_fields=["approval_status"])
        self.client.force_login(self.agency_user)

        response = self.client.get(reverse("update_exchange_rate"))

        self.assertRedirects(response, reverse("home"))


class AgencyExchangeRateResolutionTests(TestCase):
    def test_staff_inherits_its_organizations_agency_rate(self):
        user_model = get_user_model()
        agency_user = user_model.objects.create_user(
            username="resolver_agency",
            email="resolver-agency@example.com",
        )
        agency = TravelAgency.objects.create(
            admin=agency_user,
            company_code="RESOLVER",
            approval_status=True,
            exchange_rate=Decimal("1495.2500"),
        )
        organization = Organization.objects.create(
            name="Resolver Organization",
            join_code="RESOLVEORG",
            travel_agency=agency,
        )
        staff_user = user_model.objects.create_user(
            username="resolver_staff",
            email="resolver-staff@example.com",
        )
        Staff.objects.create(
            staff=staff_user,
            organization=organization,
            first_name="Rate",
            last_name="Resolver",
        )

        self.assertEqual(
            exchange_rate_for_user(staff_user),
            Decimal("1495.2500"),
        )

    def test_unassigned_user_receives_the_default_rate(self):
        user = get_user_model().objects.create_user(
            username="unassigned_rate_user",
            email="unassigned-rate@example.com",
        )

        self.assertEqual(exchange_rate_for_user(user), DEFAULT_EXCHANGE_RATE)

    def test_direct_agency_profile_takes_priority_over_other_role_mappings(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="multi_role_rate_user",
            email="multi-role-rate@example.com",
        )
        direct_agency = TravelAgency.objects.create(
            admin=user,
            company_code="DIRECTRATE",
            approval_status=True,
            exchange_rate=Decimal("1775.0000"),
        )
        other_agency_user = user_model.objects.create_user(
            username="mapped_rate_agency",
            email="mapped-rate-agency@example.com",
        )
        other_agency = TravelAgency.objects.create(
            admin=other_agency_user,
            company_code="MAPPEDRATE",
            approval_status=True,
            exchange_rate=Decimal("1400.0000"),
        )
        organization = Organization.objects.create(
            name="Other Role Organization",
            join_code="OTHERROLE",
            travel_agency=other_agency,
        )
        Staff.objects.create(
            staff=user,
            organization=organization,
            first_name="Multi",
            last_name="Role",
        )

        self.assertEqual(exchange_rate_for_user(user), direct_agency.exchange_rate)


class ExchangeRateCartTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        agency_user = user_model.objects.create_user(
            username="cart_rate_agency",
            email="cart-rate-agency@example.com",
        )
        self.agency = TravelAgency.objects.create(
            admin=agency_user,
            company_code="CARTRATE",
            approval_status=True,
            exchange_rate=Decimal("1800.0000"),
        )
        organization = Organization.objects.create(
            name="Cart Rate Organization",
            join_code="CARTRATEORG",
            travel_agency=self.agency,
        )
        self.staff_user = user_model.objects.create_user(
            username="cart_rate_staff",
            email="cart-rate-staff@example.com",
        )
        Staff.objects.create(
            staff=self.staff_user,
            organization=organization,
            first_name="Cart",
            last_name="Rate",
        )
        self.flight_data = {
            "id": "rate-offer-1",
            "source": "DUFFEL",
            "price": {"currency": "USD", "total": "10.00"},
            "travelerPricings": [{
                "fareDetailsBySegment": [{"cabin": "ECONOMY"}],
            }],
            "itineraries": [{
                "segments": [{
                    "departure": {
                        "iataCode": "LOS",
                        "at": "2030-07-10T08:00:00",
                    },
                    "arrival": {
                        "iataCode": "ACC",
                        "at": "2030-07-10T09:15:00",
                    },
                    "carrierCode": "OB",
                }],
            }],
        }

    @patch("demo.views.send_flight_pending_email")
    def test_anonymous_cart_quote_is_repriced_for_agency_before_submission(
        self,
        pending_email,
    ):
        self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )
        cart_item = self.client.session["booking_cart"]["items"][0]
        self.assertEqual(cart_item["summary"]["price"], "16,000")

        self.client.force_login(self.staff_user)
        response = self.client.post(
            reverse("book_flight"),
            {"cart_item_id": cart_item["id"]},
        )

        self.assertRedirects(response, reverse("cart_detail"))
        self.assertEqual(
            Flight_model.objects.get(user=self.staff_user).price,
            Decimal("18000.00"),
        )
        stored_items = self.client.session["booking_cart"]["items"]
        self.assertEqual(len(stored_items), 1)
        self.assertEqual(stored_items[0]["summary"]["price"], "18,000")
        cart_response = self.client.get(reverse("cart_detail"))
        flight_items = [
            item
            for item in cart_response.context["cart_items"]
            if item["type"] == "flight"
        ]
        self.assertEqual(len(flight_items), 1)
        self.assertEqual(flight_items[0]["cart_state"], "pending")
        pending_email.assert_called_once()

    def test_local_hotel_cart_price_is_rebuilt_server_side(self):
        self.client.force_login(self.staff_user)
        offer_id = "LOCAL-HOTEL-LOS-1-ROOM-1-20300710-20300712-G1"
        hotel_details = local_hotel_offer(offer_id)
        offer = hotel_details["offers"][0]
        expected_price = format_price_naira(
            offer["price"]["total"],
            offer["price"]["currency"],
            exchange_rate=self.agency.exchange_rate,
        )

        self.client.post(
            reverse("cart_add_hotel"),
            {
                "offer_id": offer_id,
                "hotel_name": "Tampered hotel",
                "description": "Tampered room",
                "check_in": "1900-01-01",
                "check_out": "1900-01-02",
                "guests": "99",
                "price": "1",
            },
        )

        summary = self.client.session["booking_cart"]["items"][0]["summary"]
        self.assertEqual(summary["price"], expected_price)
        self.assertTrue(summary["price_verified"])
        self.assertEqual(summary["hotel_name"], hotel_details["hotel"]["name"])
        self.assertEqual(summary["check_in"], "2030-07-10")


class ExchangeRatePricingTests(TestCase):
    def setUp(self):
        PriceIncrement.objects.create(id=1, increment_value=250)

    def test_usd_flight_uses_rate_before_adding_markup(self):
        total = flight_price_naira(
            {"price": {"currency": "USD", "total": "10.00"}},
            markup=250,
            exchange_rate=Decimal("1500.0000"),
        )

        self.assertEqual(total, Decimal("15250.000000"))

    def test_ngn_flight_is_not_converted_again(self):
        total = flight_price_naira(
            {"price": {"currency": "NGN", "total": "10000.00"}},
            markup=250,
            exchange_rate=Decimal("1500.0000"),
        )

        self.assertEqual(total, Decimal("10250.00"))

    def test_hotel_conversion_uses_supplied_rate(self):
        self.assertEqual(
            price_value_naira(
                "10.00",
                "USD",
                exchange_rate=Decimal("1500.0000"),
                markup=250,
            ),
            Decimal("15250.000000"),
        )
        self.assertEqual(
            price_value_naira(
                "10000.00",
                "NGN",
                exchange_rate=Decimal("1500.0000"),
                markup=250,
            ),
            Decimal("10250.00"),
        )

    def test_local_catalogue_fares_remain_native_naira(self):
        fare = SimpleNamespace(
            id=42,
            base_price_naira=Decimal("325000.00"),
            origin="LOS",
            destination="ACC",
            departure_time=time(8, 0),
            arrival_time=time(9, 15),
            return_departure_time=None,
            return_arrival_time=None,
            airline_code="OB",
            cabin="ECONOMY",
            seats_available=9,
            flight_duration="PT1H15M",
            return_duration="",
            stop_airport="",
        )

        offer = build_local_offer(
            fare,
            departure_date="2030-07-10",
            return_date=None,
            passenger_count=2,
        )

        self.assertEqual(offer["price"]["currency"], "NGN")
        self.assertEqual(offer["price"]["total"], "650000.00")
        self.assertEqual(
            flight_price_naira(
                offer,
                markup=0,
                exchange_rate=Decimal("1200.0000"),
            ),
            Decimal("650000.00"),
        )

    def test_booking_confirmation_uses_exchange_rate(self):
        order = {
            "flightOffers": [{
                "price": {"currency": "USD", "total": "10.00"},
                "itineraries": [{
                    "segments": [{
                        "departure": {
                            "iataCode": "LOS",
                            "at": "2030-07-10T08:00:00",
                        },
                        "arrival": {
                            "iataCode": "ACC",
                            "at": "2030-07-10T09:15:00",
                        },
                        "carrierCode": "OB",
                    }],
                }],
            }],
            "associatedRecords": [{
                "creationDate": "2030-07-01T10:00:00",
                "reference": "RATE01",
            }],
            "ticketingAgreement": {"option": "CONFIRMED"},
            "travelers": [{"name": {"firstName": "Ada", "lastName": "Okafor"}}],
        }

        confirmation = Booking(
            order,
            exchange_rate=Decimal("1500.0000"),
        ).construct_booking()

        self.assertEqual(confirmation["price"], 15250.0)

    def test_local_confirmation_preserves_an_approved_price_snapshot(self):
        user = get_user_model().objects.create_user(
            username="snapshot_staff",
            email="snapshot-staff@example.com",
            first_name="Ada",
        )
        offer = {
            "price": {"currency": "USD", "total": "10.00"},
            "itineraries": [{
                "segments": [{
                    "departure": {
                        "iataCode": "LOS",
                        "at": "2030-07-10T08:00:00",
                    },
                    "arrival": {
                        "iataCode": "ACC",
                        "at": "2030-07-10T09:15:00",
                    },
                    "carrierCode": "OB",
                }],
            }],
        }

        confirmation = local_booking_confirmation(
            user,
            offer,
            exchange_rate=Decimal("1900.0000"),
            confirmed_price=Decimal("15250.00"),
        )

        self.assertEqual(confirmation["price"], 15250.0)
