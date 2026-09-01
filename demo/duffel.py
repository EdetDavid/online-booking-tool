import hashlib
import json
import logging
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger(__name__)


class DuffelAPIError(Exception):
    """A safe, user-facing summary of a Duffel API failure."""


def _headers():
    token = str(getattr(settings, "DUFFEL_ACCESS_TOKEN", "") or "").strip()
    if not token:
        raise DuffelAPIError("DUFFEL_ACCESS_TOKEN is not configured.")
    return {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Duffel-Version": getattr(settings, "DUFFEL_API_VERSION", "v2"),
    }


def _request(method, path, **kwargs):
    base_url = getattr(
        settings, "DUFFEL_API_BASE_URL", "https://api.duffel.com"
    ).rstrip("/")
    timeout = getattr(settings, "FLIGHT_SEARCH_TIMEOUT_SECONDS", 25)
    verify = not getattr(settings, "FLIGHT_SEARCH_RELAX_TLS_STRICT", False)
    try:
        response = requests.request(
            method,
            f"{base_url}/{path.lstrip('/')}",
            headers=_headers(),
            timeout=timeout,
            verify=verify,
            **kwargs,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.Timeout as error:
        raise DuffelAPIError("Duffel did not respond before the search timed out.") from error
    except requests.RequestException as error:
        detail = _error_detail(getattr(error, "response", None))
        raise DuffelAPIError(detail or "Duffel flight search is unavailable.") from error
    except (TypeError, ValueError) as error:
        raise DuffelAPIError("Duffel returned an invalid response.") from error
    return payload.get("data")


def _error_detail(response):
    if response is None:
        return ""
    try:
        errors = response.json().get("errors") or []
        if errors:
            return str(errors[0].get("message") or errors[0].get("title") or "")
    except (AttributeError, TypeError, ValueError):
        pass
    return ""


def search_flights(legs, passenger_count=1, cabin="ECONOMY"):
    normalized_legs = [
        {
            "origin": str(leg["origin"]).upper(),
            "destination": str(leg["destination"]).upper(),
            "departure_date": str(leg["departure_date"]),
        }
        for leg in legs
    ]
    passenger_count = min(max(int(passenger_count or 1), 1), 9)
    body = {
        "data": {
            "slices": normalized_legs,
            "passengers": [{"type": "adult"} for _ in range(passenger_count)],
            "cabin_class": _duffel_cabin(cabin),
        }
    }
    supplier_timeout = getattr(settings, "DUFFEL_SUPPLIER_TIMEOUT_MS", 15000)
    cache_key = "duffel-offers:" + hashlib.sha256(
        json.dumps(body, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    data = _request(
        "POST",
        "air/offer_requests",
        params={
            "return_offers": "true",
            "supplier_timeout": supplier_timeout,
        },
        json=body,
    )
    offers = (data or {}).get("offers") or []
    if not getattr(settings, "ALLOW_DUFFEL_TEST_DATA", True):
        offers = [offer for offer in offers if offer.get("live_mode") is True]
    normalized = [normalize_offer(offer, passenger_count) for offer in offers]
    normalized = [offer for offer in normalized if offer.get("itineraries")]
    cache.set(
        cache_key,
        normalized,
        max(int(getattr(settings, "FLIGHT_SEARCH_CACHE_SECONDS", 60)), 0),
    )
    return normalized


def airport_suggestions(term):
    term = str(term or "").strip()
    if len(term) < 2:
        return []
    data = _request("GET", "places/suggestions", params={"query": term}) or []
    suggestions = []
    for place in data:
        code = place.get("iata_code")
        if not code:
            continue
        city_name = (place.get("city") or {}).get("name")
        label = place.get("name") or city_name or code
        if city_name and city_name.lower() not in label.lower():
            label = f"{label}, {city_name}"
        suggestions.append(f"{code}, {label}")
    return list(dict.fromkeys(suggestions))


def normalize_offer(offer, passenger_count):
    itineraries = []
    cabin = "ECONOMY"
    for slice_data in offer.get("slices") or []:
        segments = []
        for segment in slice_data.get("segments") or []:
            marketing = segment.get("marketing_carrier") or {}
            operating = segment.get("operating_carrier") or {}
            carrier_code = (
                marketing.get("iata_code")
                or operating.get("iata_code")
                or ""
            )
            passengers = segment.get("passengers") or []
            if passengers:
                cabin = _internal_cabin(
                    passengers[0].get("cabin_class")
                    or passengers[0].get("cabin_class_marketing_name")
                )
            segments.append(
                {
                    "id": segment.get("id", ""),
                    "departure": {
                        "iataCode": (segment.get("origin") or {}).get("iata_code", ""),
                        "at": segment.get("departing_at", ""),
                    },
                    "arrival": {
                        "iataCode": (segment.get("destination") or {}).get("iata_code", ""),
                        "at": segment.get("arriving_at", ""),
                    },
                    "carrierCode": carrier_code,
                    "duration": segment.get("duration", ""),
                    "operatingCarrierName": operating.get("name") or marketing.get("name") or "",
                    "flightNumber": segment.get("marketing_carrier_flight_number", ""),
                }
            )
        if segments:
            itineraries.append(
                {
                    "id": slice_data.get("id", ""),
                    "duration": slice_data.get("duration", ""),
                    "segments": segments,
                }
            )

    total = _decimal_string(offer.get("total_amount"))
    currency = str(offer.get("total_currency") or "USD").upper()
    return {
        "id": offer.get("id", ""),
        "source": "DUFFEL",
        "price": {"currency": currency, "total": total},
        "numberOfBookableSeats": offer.get("available_services_count") or 9,
        "expiresAt": offer.get("expires_at"),
        "liveMode": offer.get("live_mode"),
        "itineraries": itineraries,
        "travelerPricings": [
            {
                "travelerId": passenger.get("id", str(index + 1)),
                "travelerType": str(passenger.get("type") or "adult").upper(),
                "fareDetailsBySegment": [
                    {"segmentId": segment["id"], "cabin": cabin}
                    for itinerary in itineraries
                    for segment in itinerary["segments"]
                ],
            }
            for index, passenger in enumerate(
                (offer.get("passengers") or [{} for _ in range(passenger_count)])
            )
        ],
    }


def _duffel_cabin(value):
    normalized = str(value or "economy").strip().lower().replace("-", "_")
    return normalized if normalized in {
        "economy", "premium_economy", "business", "first"
    } else "economy"


def _internal_cabin(value):
    text = str(value or "economy").strip().upper().replace(" ", "_")
    if "PREMIUM" in text and "ECONOMY" in text:
        return "PREMIUM_ECONOMY"
    return text if text in {"ECONOMY", "BUSINESS", "FIRST"} else "ECONOMY"


def _decimal_string(value):
    try:
        return f"{Decimal(str(value)):.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "0.00"
