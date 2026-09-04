import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from django.db.models import Q

from .flight import flight_price_naira, flight_route_details
from .models import Flight_model
from .pricing import exchange_rate_for_user


CART_SESSION_KEY = "booking_cart"
MAX_CART_ITEMS = 10
DISPLAY_CART_CACHE_ATTR = "_booking_cart_display_items"
SUBMITTED_FLIGHT_STATES = {"pending", "approved"}


def cart_items(request):
    cart = request.session.get(CART_SESSION_KEY, {})
    items = cart.get("items", []) if isinstance(cart, dict) else []
    return items if isinstance(items, list) else []


def visible_cart_items(request):
    cached_items = getattr(request, DISPLAY_CART_CACHE_ATTR, None)
    if cached_items is not None:
        return cached_items

    stored_items = cart_items(request)
    items = []
    session_metadata_changed = False
    for item_index, stored_item in enumerate(stored_items):
        item = dict(stored_item)
        item["session_backed"] = True
        item["removable"] = True
        if item.get("type") == "flight":
            item["cart_state"] = "saved"
            item["bookable"] = bool(item.get("payload"))
            payload = item.get("payload")
            if isinstance(payload, dict):
                try:
                    current_summary = dict(item.get("summary") or {})
                    corrected_summary = dict(current_summary)
                    corrected_summary.update(_flight_route_summary_fields(payload))
                except (IndexError, KeyError, TypeError, ValueError):
                    pass
                else:
                    if corrected_summary != current_summary:
                        item["summary"] = corrected_summary
                        stored_items[item_index]["summary"] = corrected_summary
                        session_metadata_changed = True
        items.append(item)

    explicit_request_ids = {
        request_id
        for request_id in (
            _safe_int(item.get("flight_request_id"), None)
            for item in items
            if item.get("type") == "flight"
        )
        if request_id is not None
    }
    flight_requests = _flight_requests_for_user(request, explicit_request_ids)
    requests_by_id = {flight_request.pk: flight_request for flight_request in flight_requests}
    requests_by_signature = defaultdict(list)
    for flight_request in flight_requests:
        if flight_request.approved:
            continue
        requests_by_signature[_flight_request_signature(flight_request)].append(
            flight_request
        )

    matched_request_ids = set()
    for item_index, item in enumerate(items):
        if item.get("type") != "flight":
            continue

        flight_request = None
        request_id = _safe_int(item.get("flight_request_id"), None)
        has_explicit_request = item.get("flight_request_id") not in (None, "")
        if has_explicit_request:
            if request_id in requests_by_id:
                candidate = requests_by_id[request_id]
                if _flight_item_signature(item) == _flight_request_signature(candidate):
                    flight_request = candidate
                else:
                    continue
            else:
                continue
        else:
            signature = _flight_item_signature(item)
            candidates = [
                candidate
                for candidate in requests_by_signature.get(signature, [])
                if candidate.pk not in matched_request_ids
            ]
            if len(candidates) == 1:
                flight_request = candidates[0]

        if flight_request is None:
            continue

        matched_request_ids.add(flight_request.pk)
        item["flight_request_id"] = flight_request.pk
        if not has_explicit_request:
            stored_items[item_index]["flight_request_id"] = flight_request.pk
            session_metadata_changed = True
        item["cart_state"] = (
            "approved" if flight_request.approved else "pending"
        )
        # Submitted flight requests stay in the cart throughout approval and
        # can only be removed by a successful final booking.
        item["removable"] = False

    if session_metadata_changed:
        _save(request, stored_items)

    for flight_request in flight_requests:
        if flight_request.pk in matched_request_ids:
            continue
        items.append(_flight_request_item(flight_request))

    setattr(request, DISPLAY_CART_CACHE_ATTR, items)
    return items


def cart_count(request):
    return len(visible_cart_items(request))


def cart_total_naira(request, items=None):
    total = Decimal("0")
    for item in items if items is not None else visible_cart_items(request):
        summary = item.get("summary", {})
        total += _safe_decimal(summary.get("price"))
    return total


def flight_cart_state_counts(request, items=None):
    counts = {"saved": 0, "pending": 0, "approved": 0}
    visible_items = items if items is not None else visible_cart_items(request)
    for item in visible_items:
        if item.get("type") != "flight":
            continue
        state = item.get("cart_state", "saved")
        if state in counts:
            counts[state] += 1
    return counts


def has_removable_cart_items(request):
    return any(item.get("removable", False) for item in visible_cart_items(request))


def cart_item_is_submitted(request, item_id):
    return any(
        item.get("id") == item_id
        and item.get("cart_state") in SUBMITTED_FLIGHT_STATES
        for item in visible_cart_items(request)
    )


def get_cart_item(request, item_id):
    return next(
        (item for item in visible_cart_items(request) if item.get("id") == item_id),
        None,
    )


def add_flight(request, flight_data, flight_request_id=None):
    item = {
        "id": _item_id("flight", flight_data),
        "type": "flight",
        "summary": flight_summary(
            flight_data,
            exchange_rate=exchange_rate_for_user(request.user),
        ),
        "payload": flight_data,
        "added_at": _timestamp(),
    }
    if flight_request_id:
        item["flight_request_id"] = int(flight_request_id)
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
        "price_verified": bool(hotel_data.get("price_verified", False)),
    }
    item = {
        "id": _item_id("hotel", {"offer_id": offer_id}),
        "type": "hotel",
        "summary": normalized,
        "payload": {"offer_id": offer_id},
        "added_at": _timestamp(),
    }
    return _add_item(request, item)


def remove_item(request, item_id, allow_submitted=False):
    if not allow_submitted and cart_item_is_submitted(request, item_id):
        return False
    items = cart_items(request)
    remaining = [item for item in items if item.get("id") != item_id]
    if len(remaining) == len(items):
        return False
    _save(request, remaining)
    return True


def clear_cart(request):
    items = cart_items(request)
    submitted_item_ids = {
        item.get("id")
        for item in visible_cart_items(request)
        if item.get("session_backed")
        and item.get("cart_state") in SUBMITTED_FLIGHT_STATES
    }
    remaining = [item for item in items if item.get("id") in submitted_item_ids]
    removed_items = len(remaining) != len(items)
    if removed_items:
        _save(request, remaining)
    return removed_items


def flight_summary(flight_data, exchange_rate=None):
    itineraries = flight_data.get("itineraries") or []
    route_summary = _flight_route_summary_fields(flight_data)

    traveler_pricings = flight_data.get("travelerPricings") or []
    cabin = "ECONOMY"
    if traveler_pricings:
        fare_details = traveler_pricings[0].get("fareDetailsBySegment") or []
        if fare_details:
            cabin = fare_details[0].get("cabin") or cabin

    total_naira = flight_price_naira(
        flight_data,
        exchange_rate=exchange_rate,
    )

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
        **route_summary,
        "passengers": max(len(traveler_pricings), 1),
        "cabin": cabin.replace("_", " ").title(),
        "price": f"{total_naira.quantize(Decimal('1')):,}",
        "airlines": ", ".join(airlines) or "Airline",
        "stops": stops,
        "source": flight_data.get("source", "LIVE_FLIGHT_API"),
    }


def _flight_route_summary_fields(flight_data):
    route = flight_route_details(flight_data)
    return {
        "origin": route["origin"],
        "destination": route["destination"],
        "departure_date": route["departure_at"].split("T")[0],
        "departure_time": _time_part(route["departure_at"]),
        "arrival_time": _time_part(route["arrival_at"]),
        "return_date": route["return_at"].split("T")[0],
        "trip_type": route["trip_type"].replace("-", " ").title(),
        "legs": route["legs"],
    }


def _add_item(request, item):
    items = cart_items(request)
    for existing in items:
        if existing.get("id") != item["id"]:
            continue
        flight_request_id = item.get("flight_request_id")
        if (
            flight_request_id
            and existing.get("flight_request_id") != flight_request_id
        ):
            existing["flight_request_id"] = flight_request_id
            existing["summary"] = item["summary"]
            existing["payload"] = item["payload"]
            _save(request, items)
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
    if hasattr(request, DISPLAY_CART_CACHE_ATTR):
        delattr(request, DISPLAY_CART_CACHE_ATTR)


def _flight_requests_for_user(request, explicit_request_ids=()):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.pk:
        return []

    requester_scope = (
        Q(requested_by_staff__staff_id=user.pk)
        | Q(requested_by_staff__isnull=True, user_id=user.pk)
    )
    active_request_scope = Q(approved=False) | Q(booking_payload__isnull=False)
    if explicit_request_ids:
        active_request_scope |= Q(pk__in=explicit_request_ids)
    return list(
        Flight_model.objects.filter(requester_scope)
        .filter(booking_completed_at__isnull=True)
        .filter(active_request_scope)
        .distinct()
        .order_by("-pk")
    )


def _flight_item_signature(item):
    summary = item.get("summary") or {}
    if not summary.get("origin") or not summary.get("destination"):
        return None
    return (
        str(summary.get("origin") or "").strip().upper(),
        str(summary.get("destination") or "").strip().upper(),
        _date_value(summary.get("departure_date")),
        _date_value(summary.get("return_date")),
        _safe_int(summary.get("passengers"), 0),
        _cabin_value(summary.get("cabin")),
        _safe_decimal(summary.get("price")).quantize(Decimal("1")),
    )


def _flight_request_signature(flight_request):
    return (
        str(flight_request.origin or "").strip().upper(),
        str(flight_request.destination or "").strip().upper(),
        _date_value(flight_request.departure_date),
        _date_value(flight_request.return_date),
        flight_request.passenger_count,
        _cabin_value(flight_request.travel_class),
        _safe_decimal(flight_request.price).quantize(Decimal("1")),
    )


def _flight_request_item(flight_request):
    payload = (
        flight_request.booking_payload
        if isinstance(flight_request.booking_payload, dict)
        else None
    )
    summary = None
    if payload:
        try:
            summary = flight_summary(payload)
        except (InvalidOperation, IndexError, KeyError, TypeError, ValueError):
            summary = None

    if summary is None:
        summary = _flight_request_summary(flight_request)
    else:
        price = _safe_decimal(flight_request.price).quantize(Decimal("1"))
        summary["price"] = f"{price:,}"

    item = {
        "id": f"flight-request-{flight_request.pk}",
        "type": "flight",
        "flight_request_id": flight_request.pk,
        "cart_state": "approved" if flight_request.approved else "pending",
        "session_backed": False,
        "removable": False,
        "bookable": bool(flight_request.approved and payload),
        "summary": summary,
    }
    if payload:
        item["payload"] = payload
    return item


def _flight_request_summary(flight_request):
    price = _safe_decimal(flight_request.price).quantize(Decimal("1"))
    return {
        "origin": flight_request.origin,
        "destination": flight_request.destination,
        "departure_date": _date_value(flight_request.departure_date),
        "departure_time": "",
        "arrival_time": "",
        "return_date": _date_value(flight_request.return_date),
        "passengers": flight_request.passenger_count,
        "cabin": str(flight_request.travel_class or "Economy")
        .replace("_", " ")
        .title(),
        "price": f"{price:,}",
        "airlines": "",
        "stops": None,
        "source": "FLIGHT_REQUEST",
        "trip_type": "Round Trip" if flight_request.return_date else "One Way",
        "legs": 2 if flight_request.return_date else 1,
    }


def _date_value(value):
    if not value:
        return ""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _cabin_value(value):
    return str(value or "").strip().replace(" ", "_").upper()


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
