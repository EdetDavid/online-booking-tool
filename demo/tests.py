from django.contrib.auth import get_user_model
from django.apps import apps as django_apps
from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse
from datetime import date
from decimal import Decimal
from importlib import import_module
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

    def login_staff(self):
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
        self.client.force_login(user)
        return user

    def round_trip_flight_data(self):
        payload = json.loads(json.dumps(self.flight_data))
        payload["id"] = "CART-ROUND-TRIP-1"
        payload["tripType"] = "round-trip"
        payload["itineraries"].append(
            {
                "duration": "PT7H",
                "segments": [
                    {
                        "departure": {
                            "iataCode": "JFK",
                            "at": "2026-07-20T22:00:00",
                        },
                        "arrival": {
                            "iataCode": "LOS",
                            "at": "2026-07-21T05:00:00",
                        },
                        "carrierCode": "B6",
                        "duration": "PT7H",
                    }
                ],
            }
        )
        return payload

    def create_flight_request(self, user, **overrides):
        staff = Staff.objects.get(staff=user)
        values = {
            "user": user,
            "requested_by_staff": staff,
            "organization": staff.organization,
            "origin": "LOS",
            "destination": "JFK",
            "departure_date": date(2026, 7, 10),
            "return_date": None,
            "passenger_count": 1,
            "travel_class": "ECONOMY",
            "price": Decimal("800000.00"),
        }
        values.update(overrides)
        return Flight_model.objects.create(**values)

    def submit_and_approve_flight(self, flight_data=None):
        user = self.login_staff()
        payload = json.loads(json.dumps(flight_data or self.flight_data))
        if flight_data is None:
            payload["source"] = "LOCAL_FARE_DB"
        with patch("demo.views.send_flight_pending_email"):
            response = self.client.post(
                reverse("book_flight"),
                {"flight_data": json.dumps(payload)},
            )
        self.assertRedirects(response, reverse("cart_detail"))
        flight_request = Flight_model.objects.get(user=user)
        flight_request.approved = True
        flight_request.save(update_fields=["approved"])
        cart_item = self.client.session["booking_cart"]["items"][0]
        return user, flight_request, cart_item

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

    def test_round_trip_cart_uses_outbound_route_and_return_departure_date(self):
        flight_data = self.round_trip_flight_data()

        response = self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(flight_data)},
        )

        self.assertRedirects(response, reverse("cart_detail"))
        summary = self.client.session["booking_cart"]["items"][0]["summary"]
        self.assertEqual(summary["origin"], "LOS")
        self.assertEqual(summary["destination"], "JFK")
        self.assertEqual(summary["departure_date"], "2026-07-10")
        self.assertEqual(summary["return_date"], "2026-07-20")
        self.assertEqual(summary["departure_time"], "09:00")
        self.assertEqual(summary["arrival_time"], "15:00")

        cart_response = self.client.get(reverse("cart_detail"))
        self.assertContains(cart_response, "LOS to JFK")
        self.assertNotContains(cart_response, "LOS to LOS")

    def test_multi_city_cart_keeps_the_final_arrival_as_the_trip_end(self):
        flight_data = self.round_trip_flight_data()
        flight_data["id"] = "CART-MULTI-CITY-1"
        flight_data["tripType"] = "multi-city"
        outbound_segment = flight_data["itineraries"][0]["segments"][0]
        final_segment = flight_data["itineraries"][1]["segments"][0]
        outbound_segment["arrival"]["iataCode"] = "ACC"
        final_segment["departure"]["iataCode"] = "ACC"
        final_segment["arrival"]["iataCode"] = "JFK"

        self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(flight_data)},
        )

        summary = self.client.session["booking_cart"]["items"][0]["summary"]
        self.assertEqual(summary["origin"], "LOS")
        self.assertEqual(summary["destination"], "JFK")
        self.assertEqual(summary["arrival_time"], "05:00")
        self.assertEqual(summary["return_date"], "2026-07-21")
        self.assertEqual(summary["trip_type"], "Multi City")

    def test_cart_repairs_a_stale_round_trip_summary_in_the_session(self):
        user = self.login_staff()
        flight_data = self.round_trip_flight_data()
        self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(flight_data)},
        )
        original_item = self.client.session["booking_cart"]["items"][0]
        flight_request = self.create_flight_request(
            user,
            return_date=date(2026, 7, 20),
            booking_payload=flight_data,
        )
        session = self.client.session
        session["booking_cart"]["items"][0]["summary"].update(
            {
                "destination": "LOS",
                "arrival_time": "05:00",
                "return_date": "2026-07-21",
            }
        )
        session.save()

        response = self.client.get(reverse("cart_detail"))

        flight_items = [
            item for item in response.context["cart_items"] if item["type"] == "flight"
        ]
        self.assertEqual(len(flight_items), 1)
        self.assertEqual(flight_items[0]["cart_state"], "pending")
        self.assertEqual(flight_items[0]["flight_request_id"], flight_request.pk)
        summary = flight_items[0]["summary"]
        self.assertEqual(summary["destination"], "JFK")
        self.assertEqual(summary["arrival_time"], "15:00")
        self.assertEqual(summary["return_date"], "2026-07-20")
        stored_item = self.client.session["booking_cart"]["items"][0]
        stored_summary = stored_item["summary"]
        self.assertEqual(stored_summary["destination"], "JFK")
        self.assertEqual(stored_summary["return_date"], "2026-07-20")
        self.assertEqual(stored_item["id"], original_item["id"])
        self.assertEqual(stored_item["payload"], original_item["payload"])
        self.assertEqual(stored_summary["price"], original_item["summary"]["price"])
        self.assertEqual(stored_item["flight_request_id"], flight_request.pk)

    def test_route_data_migration_repairs_only_a_legacy_round_trip(self):
        user = self.login_staff()
        flight_data = self.round_trip_flight_data()
        legacy_request = self.create_flight_request(
            user,
            destination="LOS",
            return_date=date(2026, 7, 21),
            booking_payload=flight_data,
        )
        multi_city_payload = self.round_trip_flight_data()
        multi_city_payload["tripType"] = "multi-city"
        multi_city_request = self.create_flight_request(
            user,
            origin="ACC",
            destination="MANUAL",
            departure_date=date(2026, 8, 1),
            return_date=date(2026, 8, 9),
            booking_payload=multi_city_payload,
            price=Decimal("900000.00"),
        )
        migration = import_module(
            "demo.migrations.0013_correct_flight_route_details"
        )
        schema_editor = type(
            "SchemaEditor",
            (),
            {"connection": connection},
        )()

        migration.correct_flight_route_details(django_apps, schema_editor)
        migration.correct_flight_route_details(django_apps, schema_editor)

        legacy_request.refresh_from_db()
        self.assertEqual(legacy_request.destination, "JFK")
        self.assertEqual(legacy_request.return_date, date(2026, 7, 20))
        self.assertEqual(legacy_request.booking_payload, flight_data)
        multi_city_request.refresh_from_db()
        self.assertEqual(multi_city_request.origin, "ACC")
        self.assertEqual(multi_city_request.destination, "MANUAL")
        self.assertEqual(multi_city_request.departure_date, date(2026, 8, 1))
        self.assertEqual(multi_city_request.return_date, date(2026, 8, 9))

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
    def test_book_now_adds_unapproved_flight_to_cart(
        self,
        mock_pending_email,
    ):
        user = self.login_staff()

        response = self.client.post(
            reverse("book_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )

        self.assertRedirects(response, reverse("cart_detail"))
        flight_request = Flight_model.objects.get(
            user=user,
            origin="LOS",
            destination="JFK",
            approved=False,
        )
        items = self.client.session["booking_cart"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "flight")
        self.assertEqual(items[0]["payload"], self.flight_data)
        self.assertEqual(items[0]["flight_request_id"], flight_request.pk)
        self.assertFalse(flight_request.approved)
        mock_pending_email.assert_called_once()

    @patch("demo.views.send_flight_pending_email")
    def test_round_trip_booking_persists_the_outbound_destination(
        self,
        mock_pending_email,
    ):
        user = self.login_staff()
        flight_data = self.round_trip_flight_data()

        response = self.client.post(
            reverse("book_flight"),
            {"flight_data": json.dumps(flight_data)},
        )

        self.assertRedirects(response, reverse("cart_detail"))
        flight_request = Flight_model.objects.get(user=user)
        self.assertEqual(flight_request.origin, "LOS")
        self.assertEqual(flight_request.destination, "JFK")
        self.assertEqual(flight_request.departure_date.isoformat(), "2026-07-10")
        self.assertEqual(flight_request.return_date.isoformat(), "2026-07-20")
        mock_pending_email.assert_called_once()

    @patch("demo.views.send_flight_pending_email")
    def test_old_matching_approval_cannot_authorize_a_new_request(
        self,
        mock_pending_email,
    ):
        user = self.login_staff()
        old_approved_request = self.create_flight_request(
            user,
            approved=True,
        )

        response = self.client.post(
            reverse("book_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )

        self.assertRedirects(response, reverse("cart_detail"))
        requests = list(Flight_model.objects.filter(user=user).order_by("pk"))
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0], old_approved_request)
        self.assertTrue(requests[0].approved)
        self.assertFalse(requests[1].approved)
        self.assertEqual(
            self.client.session["booking_cart"]["items"][0]["flight_request_id"],
            requests[1].pk,
        )
        mock_pending_email.assert_called_once()

    @patch("demo.views.send_flight_pending_email")
    def test_submitting_cart_flight_keeps_item_while_approval_is_pending(
        self,
        mock_pending_email,
    ):
        user = self.login_staff()

        self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )
        original_item = self.client.session["booking_cart"]["items"][0]

        response = self.client.post(
            reverse("book_flight"),
            {"cart_item_id": original_item["id"]},
        )

        self.assertRedirects(response, reverse("cart_detail"))
        flight_request = Flight_model.objects.get(
            user=user,
            origin="LOS",
            destination="JFK",
            approved=False,
        )
        stored_items = self.client.session["booking_cart"]["items"]
        self.assertEqual(len(stored_items), 1)
        self.assertEqual(stored_items[0]["id"], original_item["id"])
        self.assertEqual(stored_items[0]["payload"], original_item["payload"])
        self.assertEqual(stored_items[0]["flight_request_id"], flight_request.pk)
        mock_pending_email.assert_called_once()

    def test_database_only_pending_flight_is_visible_locked_and_pending(self):
        user = self.login_staff()
        pending_flight = self.create_flight_request(user)

        response = self.client.get(reverse("cart_detail"))

        self.assertEqual(response.status_code, 200)
        items = list(response.context["cart_items"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "flight")
        self.assertEqual(items[0]["cart_state"], "pending")
        self.assertFalse(items[0]["removable"])
        self.assertEqual(items[0]["summary"]["origin"], pending_flight.origin)
        self.assertEqual(
            items[0]["summary"]["destination"],
            pending_flight.destination,
        )
        self.assertEqual(
            response.context["flight_status_counts"],
            {"saved": 0, "pending": 1, "approved": 0},
        )
        self.assertEqual(response.context["flight_cart_count"], 1)
        self.assertEqual(response.context["pending_cart_count"], 1)
        self.assertContains(response, "LOS to JFK")
        self.assertContains(response, 'data-approval-status="pending"')
        self.assertContains(
            response,
            'class="cart-status-pill cart-status-pill--pending"',
        )
        self.assertContains(response, 'class="fas fa-clock"')
        self.assertContains(response, "Pending approval")
        self.assertContains(
            response,
            'class="cart-state-note cart-state-note--pending"',
        )
        self.assertContains(response, 'class="fas fa-hourglass-half"')
        self.assertContains(response, "Request submitted")
        self.assertContains(response, "Waiting for administrator review.")
        self.assertNotContains(
            response,
            f'action="{reverse("book_flight")}"',
        )
        self.assertNotContains(response, "Submit for approval")
        self.assertNotContains(response, "Book flight")
        self.assertNotContains(response, 'aria-label="Remove this item"')

    def test_database_pending_flights_are_isolated_per_user_in_same_organization(self):
        owner = self.login_staff()
        organization = Staff.objects.get(staff=owner).organization
        other_user = get_user_model().objects.create_user(
            username="other_cart_staff",
            email="other-cart-staff@example.com",
            password="password-123",
        )
        Staff.objects.create(
            staff=other_user,
            organization=organization,
            first_name="Other",
            last_name="Staff",
        )
        Profile.objects.create(user=other_user)
        self.create_flight_request(owner)
        self.create_flight_request(
            other_user,
            origin="ACC",
            destination="LHR",
            price=Decimal("450000.00"),
        )

        owner_response = self.client.get(reverse("cart_detail"))
        owner_routes = {
            (item["summary"]["origin"], item["summary"]["destination"])
            for item in owner_response.context["cart_items"]
            if item["type"] == "flight"
        }

        other_client = Client()
        other_client.force_login(other_user)
        other_response = other_client.get(reverse("cart_detail"))
        other_routes = {
            (item["summary"]["origin"], item["summary"]["destination"])
            for item in other_response.context["cart_items"]
            if item["type"] == "flight"
        }

        self.assertEqual(owner_routes, {("LOS", "JFK")})
        self.assertEqual(other_routes, {("ACC", "LHR")})

    def test_matching_saved_and_database_pending_flight_is_counted_once(self):
        user = self.login_staff()
        self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )
        self.create_flight_request(user)

        response = self.client.get(reverse("cart_detail"))

        flight_items = [
            item
            for item in response.context["cart_items"]
            if item["type"] == "flight"
        ]
        self.assertEqual(len(flight_items), 1)
        self.assertEqual(flight_items[0]["cart_state"], "pending")
        self.assertEqual(response.context["cart_count"], 1)
        self.assertEqual(response.context["cart_total"], Decimal("800000.00"))

    def test_approved_database_only_flight_is_excluded_from_cart(self):
        user = self.login_staff()
        self.create_flight_request(user, approved=True)

        response = self.client.get(reverse("cart_detail"))

        self.assertEqual(list(response.context["cart_items"]), [])
        self.assertEqual(response.context["cart_count"], 0)
        self.assertEqual(response.context["cart_total"], Decimal("0"))
        self.assertNotContains(response, "LOS to JFK")

    def test_unlinked_offer_matching_old_approved_request_stays_saved(self):
        user = self.login_staff()
        self.create_flight_request(user, approved=True)
        self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )

        response = self.client.get(reverse("cart_detail"))

        flight_items = [
            item
            for item in response.context["cart_items"]
            if item["type"] == "flight"
        ]
        self.assertEqual(len(flight_items), 1)
        self.assertEqual(flight_items[0]["cart_state"], "saved")
        self.assertNotIn("flight_request_id", flight_items[0])
        self.assertTrue(flight_items[0]["removable"])
        self.assertEqual(
            response.context["flight_status_counts"],
            {"saved": 1, "pending": 0, "approved": 0},
        )
        self.assertEqual(response.context["flight_cart_count"], 1)
        self.assertEqual(response.context["pending_cart_count"], 0)
        self.assertContains(response, 'data-approval-status="saved"')
        self.assertContains(
            response,
            'class="cart-status-pill cart-status-pill--saved"',
        )
        self.assertContains(response, 'class="fas fa-bookmark"')
        self.assertContains(response, "Saved option")
        self.assertContains(response, 'class="fas fa-paper-plane"')
        self.assertContains(response, "Submit for approval")
        self.assertContains(
            response,
            f'action="{reverse("book_flight")}"',
        )
        self.assertContains(response, 'aria-label="Remove this item"')
        self.assertNotContains(
            response,
            'class="cart-status-pill cart-status-pill--approved"',
        )
        self.assertNotContains(response, "Book flight")

    def test_invalid_or_foreign_explicit_request_id_is_not_signature_remapped(self):
        owner = self.login_staff()
        organization = Staff.objects.get(staff=owner).organization
        foreign_user = get_user_model().objects.create_user(
            username="foreign_cart_staff",
            email="foreign-cart-staff@example.com",
            password="password-123",
        )
        Staff.objects.create(
            staff=foreign_user,
            organization=organization,
            first_name="Foreign",
            last_name="Staff",
        )
        Profile.objects.create(user=foreign_user)

        owner_request = self.create_flight_request(owner)
        foreign_request = self.create_flight_request(foreign_user)
        self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )
        base_item = self.client.session["booking_cart"]["items"][0]
        explicit_ids = {
            "invalid": max(owner_request.pk, foreign_request.pk) + 1000,
            "foreign": foreign_request.pk,
        }

        for case, explicit_id in explicit_ids.items():
            with self.subTest(case=case):
                tagged_item = dict(base_item)
                tagged_item["flight_request_id"] = explicit_id
                session = self.client.session
                session["booking_cart"] = {
                    "items": [tagged_item],
                    "updated_at": "test",
                }
                session.save()

                response = self.client.get(reverse("cart_detail"))
                flight_items = [
                    item
                    for item in response.context["cart_items"]
                    if item["type"] == "flight"
                ]
                saved_item = next(
                    item for item in flight_items if item["session_backed"]
                )
                pending_item = next(
                    item for item in flight_items if not item["session_backed"]
                )

                self.assertEqual(len(flight_items), 2)
                self.assertEqual(saved_item["cart_state"], "saved")
                self.assertEqual(saved_item["flight_request_id"], explicit_id)
                self.assertEqual(pending_item["cart_state"], "pending")
                self.assertEqual(
                    pending_item["flight_request_id"],
                    owner_request.pk,
                )
                self.assertEqual(
                    response.context["flight_status_counts"],
                    {"saved": 1, "pending": 1, "approved": 0},
                )

    def test_global_cart_count_context_includes_every_own_pending_flight(self):
        user = self.login_staff()
        self.create_flight_request(user)
        self.create_flight_request(
            user,
            origin="ABV",
            destination="ACC",
            departure_date=date(2026, 7, 12),
            price=Decimal("325000.00"),
        )

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cart_count"], 2)

    def test_every_pending_database_flight_appears_beyond_saved_cart_limit(self):
        user = self.login_staff()
        for index in range(11):
            self.create_flight_request(
                user,
                origin=f"A{index:02d}",
                destination=f"B{index:02d}",
                price=Decimal("100000.00") + index,
            )

        response = self.client.get(reverse("cart_detail"))

        flight_items = [
            item
            for item in response.context["cart_items"]
            if item["type"] == "flight"
        ]
        self.assertEqual(len(flight_items), 11)
        self.assertEqual(response.context["cart_count"], 11)
        self.assertTrue(
            all(item["cart_state"] == "pending" for item in flight_items)
        )

    def test_saved_pending_flight_becomes_approved_and_bookable_without_duplicate(self):
        user = self.login_staff()
        self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )
        saved_item_id = self.client.session["booking_cart"]["items"][0]["id"]
        flight_request = self.create_flight_request(user)

        pending_response = self.client.get(reverse("cart_detail"))
        pending_flights = [
            item
            for item in pending_response.context["cart_items"]
            if item["type"] == "flight"
        ]
        self.assertEqual(len(pending_flights), 1)
        self.assertEqual(pending_flights[0]["id"], saved_item_id)
        self.assertEqual(pending_flights[0]["cart_state"], "pending")
        self.assertEqual(
            pending_response.context["flight_status_counts"],
            {"saved": 0, "pending": 1, "approved": 0},
        )
        self.assertEqual(pending_response.context["flight_cart_count"], 1)
        self.assertEqual(pending_response.context["pending_cart_count"], 1)
        self.assertContains(
            pending_response,
            'class="cart-status-pill cart-status-pill--pending"',
        )
        self.assertContains(pending_response, 'class="fas fa-clock"')
        self.assertContains(pending_response, "Pending approval")
        self.assertContains(
            pending_response,
            'class="cart-state-note cart-state-note--pending"',
        )
        self.assertNotContains(
            pending_response,
            f'action="{reverse("book_flight")}"',
        )
        self.assertNotContains(
            pending_response,
            'aria-label="Remove this item"',
        )

        flight_request.approved = True
        flight_request.save(update_fields=["approved"])
        approved_response = self.client.get(reverse("cart_detail"))
        approved_flights = [
            item
            for item in approved_response.context["cart_items"]
            if item["type"] == "flight"
        ]

        self.assertEqual(len(approved_flights), 1)
        self.assertEqual(approved_flights[0]["id"], saved_item_id)
        self.assertEqual(approved_flights[0]["cart_state"], "approved")
        self.assertEqual(approved_response.context["cart_count"], 1)
        self.assertEqual(
            approved_response.context["flight_status_counts"],
            {"saved": 0, "pending": 0, "approved": 1},
        )
        self.assertEqual(approved_response.context["flight_cart_count"], 1)
        self.assertEqual(approved_response.context["pending_cart_count"], 0)
        self.assertContains(approved_response, 'data-approval-status="approved"')
        self.assertContains(
            approved_response,
            'class="cart-status-pill cart-status-pill--approved"',
        )
        self.assertContains(approved_response, 'class="fas fa-circle-check"')
        self.assertContains(approved_response, "Ready to book")
        self.assertContains(
            approved_response,
            f'action="{reverse("book_flight")}"',
        )
        self.assertContains(approved_response, 'class="fas fa-ticket"')
        self.assertContains(approved_response, "Book flight")
        self.assertNotContains(
            approved_response,
            'aria-label="Remove this item"',
        )
        self.assertNotContains(approved_response, "Submit for approval")
        self.assertNotContains(
            approved_response,
            'class="cart-state-note cart-state-note--pending"',
        )

    @patch("demo.views.send_flight_approval_email")
    @patch("demo.views.send_flight_pending_email")
    def test_admin_approval_changes_the_request_shown_to_staff(
        self,
        mock_pending_email,
        mock_approval_email,
    ):
        staff_user = self.login_staff()
        organization = Staff.objects.get(staff=staff_user).organization
        admin_user = get_user_model().objects.create_user(
            username="cart_approver",
            email="cart-approver@example.com",
            password="password-123",
        )
        admin = Admin.objects.create(
            admin=admin_user,
            organization=organization,
            first_name="Cart",
            last_name="Approver",
            approval_status=True,
        )
        Profile.objects.create(user=admin_user)

        submit_response = self.client.post(
            reverse("book_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )
        self.assertRedirects(submit_response, reverse("cart_detail"))
        stored_item = self.client.session["booking_cart"]["items"][0]
        flight_request = Flight_model.objects.get(user=staff_user)
        self.assertFalse(flight_request.approved)

        pending_cart = self.client.get(reverse("cart_detail"))
        self.assertContains(pending_cart, "Pending approval")
        self.assertContains(pending_cart, 'data-approval-status="pending"')
        pending_page = self.client.get(reverse("pending_flights"))
        self.assertContains(pending_page, "Pending approval")
        self.assertContains(pending_page, "LOS")

        admin_client = Client()
        admin_client.force_login(admin_user)
        approval_response = admin_client.post(
            reverse("approve_flight"),
            {"flight_ids": [str(flight_request.pk)]},
        )
        self.assertRedirects(approval_response, reverse("approve_flight"))

        flight_request.refresh_from_db()
        self.assertTrue(flight_request.approved)
        self.assertEqual(flight_request.approved_by_admin, admin)
        self.assertEqual(
            self.client.session["booking_cart"]["items"],
            [stored_item],
        )
        mock_pending_email.assert_called_once()
        mock_approval_email.assert_called_once_with(flight_request)

        approved_cart = self.client.get(reverse("cart_detail"))
        self.assertContains(approved_cart, 'data-approval-status="approved"')
        self.assertContains(approved_cart, "Approved")
        self.assertNotContains(approved_cart, "Pending approval")
        self.assertNotContains(approved_cart, 'aria-label="Remove this item"')
        approved_page = self.client.get(reverse("approved_flights"))
        self.assertContains(approved_page, "Approved")
        self.assertContains(approved_page, "LOS")
        self.assertNotIn(
            flight_request,
            self.client.get(reverse("pending_flights")).context["pending_flights"],
        )

    def test_approved_flight_cannot_be_removed_or_cleared_before_booking(self):
        _, flight_request, cart_item = self.submit_and_approve_flight()

        approved_cart = self.client.get(reverse("cart_detail"))
        self.assertContains(approved_cart, 'data-approval-status="approved"')
        self.assertContains(approved_cart, "Book flight")
        self.assertNotContains(approved_cart, 'aria-label="Remove this item"')

        self.client.post(reverse("cart_remove", args=[cart_item["id"]]))
        self.assertEqual(
            self.client.session["booking_cart"]["items"],
            [cart_item],
        )

        self.client.post(reverse("cart_clear"))
        self.assertEqual(
            self.client.session["booking_cart"]["items"],
            [cart_item],
        )
        flight_request.refresh_from_db()
        self.assertIsNone(flight_request.booking_completed_at)

    def test_approved_flight_is_restored_after_session_loss(self):
        user, flight_request, _ = self.submit_and_approve_flight()

        self.client.logout()
        self.client.force_login(user)
        restored_cart = self.client.get(reverse("cart_detail"))

        flight_items = [
            item
            for item in restored_cart.context["cart_items"]
            if item["type"] == "flight"
        ]
        self.assertEqual(len(flight_items), 1)
        self.assertEqual(
            flight_items[0]["flight_request_id"],
            flight_request.pk,
        )
        self.assertEqual(flight_items[0]["cart_state"], "approved")
        self.assertTrue(flight_items[0]["bookable"])
        self.assertContains(restored_cart, "Book flight")

        with patch("demo.views.send_flight_email"):
            booking_response = self.client.post(
                reverse("book_flight"),
                {"cart_item_id": flight_items[0]["id"]},
            )
        self.assertEqual(booking_response.status_code, 200)
        flight_request.refresh_from_db()
        self.assertIsNotNone(flight_request.booking_completed_at)
        self.assertEqual(
            list(self.client.get(reverse("cart_detail")).context["cart_items"]),
            [],
        )

    def test_successful_approved_local_booking_removes_the_cart_item(self):
        _, flight_request, cart_item = self.submit_and_approve_flight()

        with patch("demo.views.send_flight_email") as mock_email:
            response = self.client.post(
                reverse("book_flight"),
                {"cart_item_id": cart_item["id"]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "demo/book_flight.html")
        self.assertEqual(self.client.session["booking_cart"]["items"], [])
        flight_request.refresh_from_db()
        self.assertIsNotNone(flight_request.booking_completed_at)
        mock_email.assert_called_once()

    def test_failed_approved_local_booking_remains_in_the_cart(self):
        _, flight_request, cart_item = self.submit_and_approve_flight()

        with patch(
            "demo.views.local_booking_confirmation",
            side_effect=RuntimeError("local confirmation failed"),
        ):
            response = self.client.post(
                reverse("book_flight"),
                {"cart_item_id": cart_item["id"]},
            )

        self.assertRedirects(response, reverse("cart_detail"))
        self.assertEqual(
            self.client.session["booking_cart"]["items"],
            [cart_item],
        )
        flight_request.refresh_from_db()
        self.assertIsNone(flight_request.booking_completed_at)
        retry_cart = self.client.get(reverse("cart_detail"))
        self.assertContains(retry_cart, 'data-approval-status="approved"')
        self.assertContains(retry_cart, "Book flight")

    def test_confirmation_email_failure_does_not_restore_a_booked_flight(self):
        _, flight_request, cart_item = self.submit_and_approve_flight()

        with patch(
            "demo.views.send_flight_email",
            side_effect=RuntimeError("email unavailable"),
        ):
            response = self.client.post(
                reverse("book_flight"),
                {"cart_item_id": cart_item["id"]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["booking_cart"]["items"], [])
        flight_request.refresh_from_db()
        self.assertIsNotNone(flight_request.booking_completed_at)

    def test_failed_approved_amadeus_booking_remains_in_the_cart(self):
        flight_data = json.loads(json.dumps(self.flight_data))
        flight_data["source"] = "AMADEUS"
        _, flight_request, cart_item = self.submit_and_approve_flight(flight_data)

        with patch(
            "demo.views.get_access_token",
            side_effect=RuntimeError("provider unavailable"),
        ), patch("demo.views.send_flight_email_2") as mock_fallback_email:
            response = self.client.post(
                reverse("book_flight"),
                {"cart_item_id": cart_item["id"]},
            )

        self.assertRedirects(response, reverse("cart_detail"))
        self.assertEqual(
            self.client.session["booking_cart"]["items"],
            [cart_item],
        )
        flight_request.refresh_from_db()
        self.assertIsNone(flight_request.booking_completed_at)
        mock_fallback_email.assert_not_called()

    def test_successful_approved_amadeus_booking_removes_the_cart_item(self):
        flight_data = json.loads(json.dumps(self.flight_data))
        flight_data["source"] = "AMADEUS"
        _, flight_request, cart_item = self.submit_and_approve_flight(flight_data)

        with patch("demo.views.get_access_token", return_value="token"), patch(
            "demo.views.amadeus.shopping.flight_offers.pricing.post"
        ) as mock_pricing, patch("demo.views.requests.post") as mock_order, patch(
            "demo.views.Booking.construct_booking",
            return_value={"reference": "ORDER-123", "confirmed": "CONFIRMED"},
        ), patch("demo.views.send_flight_email") as mock_email:
            mock_pricing.return_value.data = {"flightOffers": [flight_data]}
            mock_order.return_value.raise_for_status.return_value = None
            mock_order.return_value.json.return_value = {
                "data": {"id": "ORDER-123"},
            }
            response = self.client.post(
                reverse("book_flight"),
                {"cart_item_id": cart_item["id"]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["booking_cart"]["items"], [])
        flight_request.refresh_from_db()
        self.assertIsNotNone(flight_request.booking_completed_at)
        mock_order.assert_called_once()
        mock_email.assert_called_once()

    @patch("demo.views.requests.post")
    @patch("demo.views.amadeus.shopping.flight_offers.pricing.post")
    @patch("demo.views.get_access_token")
    @patch("demo.views.send_flight_email_2", return_value=1)
    def test_approved_duffel_booking_is_emailed_without_provider_order(
        self,
        mock_email,
        mock_access_token,
        mock_pricing,
        mock_order,
    ):
        flight_data = json.loads(json.dumps(self.flight_data))
        flight_data["source"] = "DUFFEL"
        user, flight_request, cart_item = self.submit_and_approve_flight(flight_data)

        response = self.client.post(
            reverse("book_flight"),
            {"cart_item_id": cart_item["id"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "demo/success_page.html")
        self.assertContains(response, "Booking request sent!")
        self.assertEqual(self.client.session["booking_cart"]["items"], [])
        flight_request.refresh_from_db()
        self.assertIsNotNone(flight_request.booking_completed_at)
        mock_email.assert_called_once_with(
            user,
            "LOS",
            "JFK",
            "2026-07-10",
            None,
            "ECONOMY",
            flight_request,
        )
        mock_access_token.assert_not_called()
        mock_pricing.assert_not_called()
        mock_order.assert_not_called()

    @patch(
        "demo.views.send_flight_email_2",
        side_effect=RuntimeError("email unavailable"),
    )
    def test_failed_duffel_booking_email_remains_in_the_cart(self, mock_email):
        flight_data = json.loads(json.dumps(self.flight_data))
        flight_data["source"] = "DUFFEL"
        _, flight_request, cart_item = self.submit_and_approve_flight(flight_data)

        response = self.client.post(
            reverse("book_flight"),
            {"cart_item_id": cart_item["id"]},
        )

        self.assertRedirects(response, reverse("cart_detail"))
        self.assertEqual(
            self.client.session["booking_cart"]["items"],
            [cart_item],
        )
        flight_request.refresh_from_db()
        self.assertIsNone(flight_request.booking_completed_at)
        mock_email.assert_called_once()

    def test_remove_and_clear_keep_pending_flight_but_remove_saved_items(self):
        user = self.login_staff()
        self.client.post(
            reverse("cart_add_flight"),
            {"flight_data": json.dumps(self.flight_data)},
        )
        self.create_flight_request(user)
        hotel_data = {
            "offer_id": "LOCAL-HOTEL-LOS-PENDING-1",
            "hotel_name": "Pending Trip Hotel",
            "description": "Executive room",
            "check_in": "2026-07-10",
            "check_out": "2026-07-12",
            "guests": "1",
            "price": "250,000",
        }
        self.client.post(reverse("cart_add_hotel"), hotel_data)

        response = self.client.get(reverse("cart_detail"))
        pending_item = next(
            item
            for item in response.context["cart_items"]
            if item["type"] == "flight"
        )
        saved_hotel = next(
            item
            for item in self.client.session["booking_cart"]["items"]
            if item["type"] == "hotel"
        )
        saved_flight = next(
            item
            for item in self.client.session["booking_cart"]["items"]
            if item["type"] == "flight"
        )

        self.client.post(reverse("cart_remove", args=[pending_item["id"]]))
        response = self.client.get(reverse("cart_detail"))
        self.assertEqual(
            len(
                [
                    item
                    for item in response.context["cart_items"]
                    if item["type"] == "flight"
                ]
            ),
            1,
        )

        self.client.post(reverse("cart_remove", args=[saved_hotel["id"]]))
        response = self.client.get(reverse("cart_detail"))
        self.assertEqual(
            [item["type"] for item in response.context["cart_items"]],
            ["flight"],
        )

        self.client.post(reverse("cart_add_hotel"), hotel_data)
        self.client.post(reverse("cart_clear"))
        response = self.client.get(reverse("cart_detail"))
        self.assertEqual(
            [item["type"] for item in response.context["cart_items"]],
            ["flight"],
        )
        self.assertEqual(
            self.client.session["booking_cart"]["items"],
            [saved_flight],
        )


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
                "Departuredate": "2030-07-10",
                "Returndate": "2030-07-18",
                "passengerCount": "1",
                "cabinClassTop": "economy",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-trip-type="one-way"', count=18)
        self.assertContains(response, '<div class="leg-label">Depart</div>')
        self.assertNotContains(response, '<div class="leg-label">Return</div>')

    def test_round_trip_search_returns_depart_and_return_legs(self):
        response = self.client.post(
            reverse("home"),
            {
                "tripType": "round-trip",
                "Origin": "LOS",
                "Destination": "JFK",
                "Departuredate": "2030-07-10",
                "Returndate": "2030-07-18",
                "passengerCount": "2",
                "cabinClassTop": "business",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-trip-type="round-trip"', count=18)
        self.assertContains(response, '<div class="leg-label">Depart</div>')
        self.assertContains(response, '<div class="leg-label">Return</div>')

    def test_multi_city_search_returns_every_requested_leg(self):
        response = self.client.post(
            reverse("home"),
            {
                "tripType": "multi-city",
                "multi_origin": ["LOS", "ACC", "LHR"],
                "multi_destination": ["ACC", "LHR", "JFK"],
                "multi_date": ["2030-07-10", "2030-07-14", "2030-07-20"],
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
                "multi_date": ["2030-07-20", "2030-07-14"],
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
                    "departure_date": "2030-07-10",
                },
                {
                    "origin": "ACC",
                    "destination": "LHR",
                    "departure_date": "2030-07-14",
                },
                {
                    "origin": "LHR",
                    "destination": "JFK",
                    "departure_date": "2030-07-20",
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

        self.assertRedirects(response, reverse("cart_detail"))
        request = Flight_model.objects.get(user=self.user)
        self.assertEqual(request.origin, "LOS")
        self.assertEqual(request.destination, "JFK")
        self.assertEqual(request.return_date.isoformat(), "2030-07-20")
        self.assertEqual(
            len(self.client.session["booking_cart"]["items"]),
            1,
        )
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
                "Checkindate": "2030-07-12",
                "Checkoutdate": "2030-07-10",
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
                "Checkindate": "2030-07-10",
                "Checkoutdate": "2030-07-12",
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
        self.assertEqual(flight.approved_by_admin, self.org_a_admin)
        mock_send_email.assert_called_once()
        self.assertEqual(
            mock_send_email.call_args.args[3],
            ["corp-staff@example.com", "managed-agency@example.com"],
        )

        mock_send_email.reset_mock()
        repeat_response = self.client.post(
            reverse("approve_flight"),
            {"flight_ids": [str(flight.id)]},
        )
        self.assertRedirects(repeat_response, reverse("approve_flight"))
        mock_send_email.assert_not_called()

    @patch("demo.views.send_html_email")
    def test_admin_cannot_approve_another_organizations_flight(
        self,
        mock_send_email,
    ):
        self.client.force_login(self.admin.admin)

        response = self.client.post(
            reverse("approve_flight"),
            {"flight_ids": [str(self.managed_flight.id)]},
        )

        self.assertRedirects(response, reverse("approve_flight"))
        self.managed_flight.refresh_from_db()
        self.assertFalse(self.managed_flight.approved)
        self.assertIsNone(self.managed_flight.approved_by_admin)
        mock_send_email.assert_not_called()

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

    def test_unapproved_admin_cannot_approve_flights_directly(self):
        unapproved_user = get_user_model().objects.create_user(
            username="guard_unapproved_admin",
            email="guard-unapproved-admin@example.com",
            password="password-123",
        )
        Admin.objects.create(
            admin=unapproved_user,
            organization=self.organization,
            first_name="Pending",
            last_name="Admin",
            approval_status=False,
        )
        flight = Flight_model.objects.create(
            user=self.staff_user,
            requested_by_staff=self.staff,
            organization=self.organization,
            origin="LOS",
            destination="JFK",
            departure_date=date(2030, 7, 10),
            passenger_count=1,
            travel_class="ECONOMY",
            price=Decimal("800000.00"),
        )
        self.client.force_login(unapproved_user)

        response = self.client.post(
            reverse("approve_flight"),
            {"flight_ids": [str(flight.pk)]},
        )

        self.assertRedirects(response, reverse("home"))
        flight.refresh_from_db()
        self.assertFalse(flight.approved)
        self.assertIsNone(flight.approved_by_admin)
