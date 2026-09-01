from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .duffel import (
    DuffelAPIError,
    airport_suggestions,
    normalize_offer,
    search_flights,
)
from .flight import flight_price_naira


DUFFEL_OFFER = {
    "id": "off_test_123",
    "total_amount": "125.50",
    "total_currency": "USD",
    "expires_at": "2026-09-01T12:00:00Z",
    "live_mode": False,
    "passengers": [{"id": "pas_test_123", "type": "adult"}],
    "slices": [
        {
            "id": "sli_test_123",
            "duration": "PT1H15M",
            "segments": [
                {
                    "id": "seg_test_123",
                    "departing_at": "2026-09-20T09:00:00",
                    "arriving_at": "2026-09-20T10:15:00",
                    "duration": "PT1H15M",
                    "origin": {"iata_code": "LOS"},
                    "destination": {"iata_code": "ABV"},
                    "marketing_carrier": {
                        "iata_code": "ZZ",
                        "name": "Duffel Airways",
                    },
                    "operating_carrier": {
                        "iata_code": "ZZ",
                        "name": "Duffel Airways",
                    },
                    "marketing_carrier_flight_number": "101",
                    "passengers": [{"cabin_class": "economy"}],
                }
            ],
        }
    ],
}


class DuffelAdapterTests(SimpleTestCase):
    def test_normalizes_duffel_offer_for_existing_flight_ui(self):
        result = normalize_offer(DUFFEL_OFFER, passenger_count=1)

        self.assertEqual(result["source"], "DUFFEL")
        self.assertEqual(result["price"], {"currency": "USD", "total": "125.50"})
        self.assertEqual(
            result["itineraries"][0]["segments"][0]["departure"]["iataCode"],
            "LOS",
        )
        self.assertEqual(
            result["travelerPricings"][0]["fareDetailsBySegment"][0]["cabin"],
            "ECONOMY",
        )

    def test_currency_conversion_does_not_multiply_naira_again(self):
        self.assertEqual(
            flight_price_naira(
                {"price": {"total": "200000", "currency": "NGN"}},
                markup=0,
            ),
            200000,
        )


@override_settings(
    DUFFEL_ACCESS_TOKEN="duffel_test_token",
    DUFFEL_API_BASE_URL="https://api.duffel.test",
    DUFFEL_API_VERSION="v2",
    DUFFEL_SUPPLIER_TIMEOUT_MS=10000,
    FLIGHT_SEARCH_TIMEOUT_SECONDS=20,
    FLIGHT_SEARCH_CACHE_SECONDS=60,
    FLIGHT_SEARCH_RELAX_TLS_STRICT=False,
    ALLOW_DUFFEL_TEST_DATA=True,
)
class DuffelClientTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("demo.duffel.requests.request")
    def test_offer_request_uses_duffel_v2_contract(self, request):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": {"offers": [DUFFEL_OFFER]}}
        request.return_value = response

        offers = search_flights(
            [{
                "origin": "LOS",
                "destination": "ABV",
                "departure_date": "2026-09-20",
            }],
            passenger_count=1,
            cabin="ECONOMY",
        )

        self.assertEqual(offers[0]["id"], "off_test_123")
        call = request.call_args
        self.assertEqual(call.args[:2], ("POST", "https://api.duffel.test/air/offer_requests"))
        self.assertEqual(call.kwargs["headers"]["Duffel-Version"], "v2")
        self.assertEqual(call.kwargs["json"]["data"]["passengers"], [{"type": "adult"}])
        self.assertEqual(call.kwargs["json"]["data"]["cabin_class"], "economy")

    @patch("demo.duffel.requests.request")
    def test_place_suggestions_are_formatted_for_existing_autocomplete(self, request):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": [{
                "iata_code": "LOS",
                "name": "Murtala Muhammed International Airport",
                "city": {"name": "Lagos"},
            }]
        }
        request.return_value = response

        self.assertEqual(
            airport_suggestions("Lagos"),
            ["LOS, Murtala Muhammed International Airport, Lagos"],
        )


@override_settings(
    USE_LIVE_FLIGHT_API=True,
    FLIGHT_SEARCH_PROVIDER="duffel",
    MIN_FLIGHT_RESULTS=18,
)
class DuffelSearchViewTests(TestCase):
    @patch("demo.views.local_flight_search")
    @patch("demo.views.duffel_flight_search")
    def test_reachable_duffel_is_not_supplemented_with_local_fares(
        self,
        search,
        local_search,
    ):
        offer = normalize_offer(DUFFEL_OFFER, passenger_count=1)
        search.return_value = [offer]

        response = self.client.post(
            reverse("home"),
            {
                "tripType": "one-way",
                "Origin": "LOS",
                "Destination": "ABV",
                "Departuredate": "2026-09-20",
                "passengerCount": "1",
                "cabinClassTop": "economy",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live Duffel fare")
        self.assertContains(response, "Operated by Duffel Airways")
        self.assertContains(response, "flight-result-card", count=1)
        local_search.assert_not_called()
        search.assert_called_once_with(
            legs=[{
                "origin": "LOS",
                "destination": "ABV",
                "departure_date": "2026-09-20",
            }],
            passenger_count=1,
            cabin="ECONOMY",
        )

    @patch("demo.views.local_flight_search")
    @patch("demo.views.duffel_flight_search", return_value=[])
    def test_reachable_duffel_with_no_offers_does_not_use_local_fares(
        self,
        search,
        local_search,
    ):
        response = self._standard_search()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No flight itinerary was found")
        self.assertNotContains(response, "flight-result-card")
        local_search.assert_not_called()

    @patch("demo.views.local_flight_search")
    @patch(
        "demo.views.duffel_flight_search",
        side_effect=DuffelAPIError("Duffel is unavailable"),
    )
    def test_unreachable_duffel_uses_local_fares(self, search, local_search):
        local_offer = normalize_offer(DUFFEL_OFFER, passenger_count=1)
        local_offer.update({"id": "LOCAL-1", "source": "LOCAL_FARE_DB"})
        local_search.return_value = [local_offer]

        response = self._standard_search()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Local fare")
        local_search.assert_called_once()

    @patch("demo.views.local_multi_city_search")
    @patch("demo.views.duffel_flight_search")
    def test_reachable_duffel_multi_city_does_not_use_local_fares(
        self,
        search,
        local_search,
    ):
        search.return_value = [normalize_offer(DUFFEL_OFFER, passenger_count=1)]

        response = self.client.post(
            reverse("home"),
            {
                "tripType": "multi-city",
                "multi_origin": ["LOS", "ABV"],
                "multi_destination": ["ABV", "ACC"],
                "multi_date": ["2026-09-20", "2026-09-23"],
                "passengerCount": "1",
                "cabinClassTop": "economy",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live Duffel fare")
        local_search.assert_not_called()

    def _standard_search(self):
        return self.client.post(
            reverse("home"),
            {
                "tripType": "one-way",
                "Origin": "LOS",
                "Destination": "ABV",
                "Departuredate": "2026-09-20",
                "passengerCount": "1",
                "cabinClassTop": "economy",
            },
        )

    @patch("demo.views.local_airport_search")
    @patch("demo.views.airport_suggestions")
    def test_autocomplete_uses_only_duffel_when_reachable(
        self,
        suggestions,
        local_search,
    ):
        suggestions.return_value = ["LOS, Murtala Muhammed Airport, Lagos"]

        response = self.client.get(
            reverse("origin_airport_search"),
            {"term": "Lagos"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("LOS, Murtala Muhammed Airport, Lagos", response.json())
        suggestions.assert_called_once_with("Lagos")
        local_search.assert_not_called()

    @patch(
        "demo.views.airport_suggestions",
        side_effect=DuffelAPIError("Duffel is unavailable"),
    )
    @patch(
        "demo.views.local_airport_search",
        return_value=["LOS, Local Lagos Airport"],
    )
    def test_autocomplete_uses_local_data_when_duffel_is_unreachable(
        self,
        local_search,
        suggestions,
    ):
        response = self.client.get(
            reverse("origin_airport_search"),
            {"term": "Lagos"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["LOS, Local Lagos Airport"])
        local_search.assert_called_once_with("Lagos")
