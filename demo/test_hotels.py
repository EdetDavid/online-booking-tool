from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse


def future_stay():
    checkin = date.today() + timedelta(days=14)
    checkout = checkin + timedelta(days=3)
    return checkin.isoformat(), checkout.isoformat()


def hotel_search_payload():
    checkin, checkout = future_stay()
    return {
        "Origin": "LOS",
        "Checkindate": checkin,
        "Checkoutdate": checkout,
        "guestCount": "2",
    }


@override_settings(MIN_HOTEL_RESULTS=12)
class HotelFallbackTests(TestCase):
    @override_settings(
        HOTEL_SEARCH_PROVIDER="local",
        USE_LIVE_HOTEL_API=True,
    )
    @patch("demo.views.amadeus.reference_data.locations.hotels.by_city.get")
    def test_local_provider_uses_standalone_inventory_immediately(
        self,
        live_search,
    ):
        response = self.client.post(reverse("hotel"), hotel_search_payload())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "stay-result-card", count=12)
        self.assertContains(response, "Showing standalone hotel inventory")
        live_search.assert_not_called()

    @override_settings(
        HOTEL_SEARCH_PROVIDER="amadeus",
        USE_LIVE_HOTEL_API=True,
    )
    @patch(
        "demo.views.amadeus.reference_data.locations.hotels.by_city.get",
        side_effect=RuntimeError("provider offline"),
    )
    def test_provider_failure_uses_standalone_inventory(self, live_search):
        response = self.client.post(reverse("hotel"), hotel_search_payload())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "stay-result-card", count=12)
        self.assertContains(response, "Live hotel search is unavailable")

    @override_settings(
        HOTEL_SEARCH_PROVIDER="amadeus",
        USE_LIVE_HOTEL_API=True,
    )
    @patch("demo.views.amadeus.reference_data.locations.hotels.by_city.get")
    def test_empty_live_inventory_uses_standalone_inventory(self, live_search):
        live_search.return_value = SimpleNamespace(data=[])

        response = self.client.post(reverse("hotel"), hotel_search_payload())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "stay-result-card", count=12)
        self.assertContains(response, "No live hotel inventory was returned")

    @override_settings(
        HOTEL_SEARCH_PROVIDER="amadeus",
        USE_LIVE_HOTEL_API=True,
    )
    @patch("demo.views.amadeus.shopping.hotel_offers_search.get")
    @patch("demo.views.amadeus.reference_data.locations.hotels.by_city.get")
    def test_unusable_live_records_use_standalone_inventory(
        self,
        hotel_list_search,
        offer_search,
    ):
        hotel_list_search.return_value = SimpleNamespace(
            data=[{"hotelId": "BROKEN-1"}]
        )
        offer_search.return_value = SimpleNamespace(
            data=[{"hotel": {}, "offers": []}]
        )

        response = self.client.post(reverse("hotel"), hotel_search_payload())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "stay-result-card", count=12)
        self.assertContains(response, "Live hotel results could not be displayed")

    @override_settings(
        HOTEL_SEARCH_PROVIDER="amadeus",
        USE_LIVE_HOTEL_API=True,
    )
    @patch("demo.views.local_hotel_search")
    @patch("demo.views.amadeus.shopping.hotel_offers_search.get")
    @patch("demo.views.amadeus.reference_data.locations.hotels.by_city.get")
    def test_usable_live_inventory_is_not_replaced_by_standalone_results(
        self,
        hotel_list_search,
        offer_search,
        local_search,
    ):
        checkin, checkout = future_stay()
        hotel_list_search.return_value = SimpleNamespace(
            data=[{"hotelId": "LIVE-LOS-1"}]
        )
        offer_search.return_value = SimpleNamespace(
            data=[{
                "source": "LIVE_HOTEL_API",
                "hotel": {
                    "hotelId": "LIVE-LOS-1",
                    "name": "Live Lagos Hotel",
                    "latitude": 6.5,
                    "longitude": 3.4,
                    "address": "Victoria Island, Lagos",
                },
                "offers": [{
                    "id": "LIVE-OFFER-1",
                    "price": {"currency": "USD", "total": "200.00"},
                    "checkInDate": checkin,
                    "checkOutDate": checkout,
                }],
            }]
        )

        response = self.client.post(reverse("hotel"), hotel_search_payload())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live Lagos Hotel")
        self.assertContains(response, "stay-result-card", count=1)
        local_search.assert_not_called()

    @override_settings(
        HOTEL_SEARCH_PROVIDER="local",
        USE_LIVE_HOTEL_API=True,
    )
    @patch("demo.views.amadeus.reference_data.locations.get")
    def test_local_city_autocomplete_does_not_call_online_provider(
        self,
        live_search,
    ):
        response = self.client.get(
            reverse("city_search"),
            {"term": "Lagos"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item.startswith("LOS,") for item in response.json()))
        live_search.assert_not_called()
