import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from .models import PriceIncrement


CART_SESSION_KEY = "booking_cart"
MAX_CART_ITEMS = 10


def cart_items(request):
    cart = request.session.get(CART_SESSION_KEY, {})
    items = cart.get("items", []) if isinstance(cart, dict) else []
    return items if isinstance(items, list) else []


def cart_count(request):
    return len(cart_items(request))


def cart_total_naira(request):
    total = Decimal("0")
    for item in cart_items(request):
        summary = item.get("summary", {})
        total += _safe_decimal(summary.get("price"))
    return total


def get_cart_item(request, item_id):
    return next(
        (item for item in cart_items(request) if item.get("id") == item_id),
        None,
    )


def add_flight(request, flight_data):
    item = {
        "id": _item_id("flight", flight_data),
        "type": "flight",
        "summary": flight_summary(flight_data),
        "payload": flight_data,
        "added_at": _timestamp(),
    }
    return _add_item(request, item)


def add_hotel(request, hotel_data):
    offer_id = str(hotel_data.get("offer_id") or "").strip()
    if not offer_id:
        raise ValueError("A hotel offer is required.")

    normalized = {
        "offer_id": offer_id,
        "hotel_name": str(hotel_data.get("hotel_name") or "Hotel stay").strip(),
        "description": str(hotel_data.get("description") or "Hotel room").strip(),
        "check_in": str(hotel_data.get("check_in") or "").strip(),
        "check_out": str(hotel_data.get("check_out") or "").strip(),
        "guests": max(_safe_int(hotel_data.get("guests"), 1), 1),
        "price": str(hotel_data.get("price") or "0").strip(),
    }
    item = {
        "id": _item_id("hotel", {"offer_id": offer_id}),
        "type": "hotel",
        "summary": normalized,
        "payload": {"offer_id": offer_id},
        "added_at": _timestamp(),
    }
    return _add_item(request, item)


def remove_item(request, item_id):
    items = cart_items(request)
    remaining = [item for item in items if item.get("id") != item_id]
    if len(remaining) == len(items):
        return False
    _save(request, remaining)
    return True


def clear_cart(request):
    had_items = bool(cart_items(request))
    _save(request, [])
    return had_items


def flight_summary(flight_data):
    itineraries = flight_data.get("itineraries") or []
    first_itinerary = itineraries[0]
    first_segments = first_itinerary.get("segments") or []
    first_segment = first_segments[0]
    final_itinerary = itineraries[-1]
    final_segments = final_itinerary.get("segments") or []
    last_trip_segment = final_segments[-1]
    trip_type = flight_data.get(
        "tripType",
        "round-trip" if len(itineraries) > 1 else "one-way",
    )

    traveler_pricings = flight_data.get("travelerPricings") or []
    cabin = "ECONOMY"
    if traveler_pricings:
        fare_details = traveler_pricings[0].get("fareDetailsBySegment") or []
        if fare_details:
            cabin = fare_details[0].get("cabin") or cabin

    return_date = ""
    if trip_type in {"round-trip", "multi-city"} and final_segments:
        return_date = (
            last_trip_segment.get("arrival", {}).get("at", "").split("T")[0]
        )

    price = _safe_decimal(flight_data.get("price", {}).get("total"))
    increment = PriceIncrement.objects.first()
    markup = Decimal(str(increment.increment_value or 0)) if increment else Decimal("0")
    total_naira = (price * Decimal("1600")) + markup

    airlines = []
    stops = 0
    for itinerary in itineraries:
        segments = itinerary.get("segments") or []
        stops += max(len(segments) - 1, 0)
        for segment in segments:
            carrier = segment.get("carrierCode")
            if carrier and carrier not in airlines:
                airlines.append(carrier)

    return {
        "origin": first_segment.get("departure", {}).get("iataCode", ""),
        "destination": last_trip_segment.get("arrival", {}).get("iataCode", ""),
        "departure_date": first_segment.get("departure", {}).get("at", "").split("T")[0],
        "departure_time": _time_part(
            first_segment.get("departure", {}).get("at", "")
        ),
        "arrival_time": _time_part(
            last_trip_segment.get("arrival", {}).get("at", "")
        ),
        "return_date": return_date,
        "passengers": max(len(traveler_pricings), 1),
        "cabin": cabin.replace("_", " ").title(),
        "price": f"{total_naira.quantize(Decimal('1')):,}",
        "airlines": ", ".join(airlines) or "Airline",
        "stops": stops,
        "source": flight_data.get("source", "LIVE_FLIGHT_API"),
        "trip_type": trip_type.replace("-", " ").title(),
        "legs": len(itineraries),
    }


def _add_item(request, item):
    items = cart_items(request)
    if any(existing.get("id") == item["id"] for existing in items):
        return False
    if len(items) >= MAX_CART_ITEMS:
        raise ValueError(f"Your cart can hold up to {MAX_CART_ITEMS} items.")
    items.append(item)
    _save(request, items)
    return True


def _save(request, items):
    request.session[CART_SESSION_KEY] = {
        "items": items,
        "updated_at": _timestamp(),
    }
    request.session.modified = True


def _item_id(item_type, payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    return f"{item_type}-{digest}"


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _safe_decimal(value):
    try:
        return Decimal(str(value or "0").replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _time_part(value):
    parts = str(value or "").split("T", 1)
    return parts[1][:5] if len(parts) > 1 else ""
