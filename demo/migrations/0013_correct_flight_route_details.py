from datetime import date
import re

from django.db import migrations


def _date_from_timestamp(value):
    date_text = str(value or "").split("T", 1)[0]
    try:
        return date.fromisoformat(date_text)
    except (TypeError, ValueError):
        return None


def _iata_code(value):
    code = str(value or "").strip().upper()
    return code if re.fullmatch(r"[A-Z]{3}", code) else None


def correct_flight_route_details(apps, schema_editor):
    flight_model = apps.get_model("demo", "Flight_model")
    database_alias = schema_editor.connection.alias

    for flight_request in flight_model.objects.using(database_alias).exclude(
        booking_payload__isnull=True
    ).iterator(chunk_size=200):
        payload = flight_request.booking_payload
        if (
            not isinstance(payload, dict)
            or str(payload.get("tripType") or "").strip().lower() != "round-trip"
        ):
            continue

        itineraries = payload.get("itineraries") or []
        if (
            not isinstance(itineraries, list)
            or len(itineraries) != 2
            or not all(isinstance(itinerary, dict) for itinerary in itineraries)
        ):
            continue

        outbound_segments = itineraries[0].get("segments") or []
        final_segments = itineraries[-1].get("segments") or []
        if (
            not isinstance(outbound_segments, list)
            or not isinstance(final_segments, list)
            or not outbound_segments
            or not final_segments
            or not all(isinstance(segment, dict) for segment in outbound_segments)
            or not all(isinstance(segment, dict) for segment in final_segments)
        ):
            continue

        outbound_first = outbound_segments[0]
        outbound_last = outbound_segments[-1]
        inbound_first = final_segments[0]
        inbound_last = final_segments[-1]

        payload_origin = _iata_code(
            outbound_first.get("departure", {}).get("iataCode")
        )
        expected_destination = _iata_code(
            outbound_last.get("arrival", {}).get("iataCode")
        )
        legacy_destination = _iata_code(
            inbound_last.get("arrival", {}).get("iataCode")
        )
        payload_departure_date = _date_from_timestamp(
            outbound_first.get("departure", {}).get("at")
        )
        expected_return_date = _date_from_timestamp(
            inbound_first.get("departure", {}).get("at")
        )
        legacy_return_date = _date_from_timestamp(
            inbound_last.get("arrival", {}).get("at")
        )

        if (
            not payload_origin
            or not expected_destination
            or not legacy_destination
            or not payload_departure_date
            or not expected_return_date
            or not legacy_return_date
            or str(flight_request.origin or "").strip().upper() != payload_origin
            or flight_request.departure_date != payload_departure_date
        ):
            continue

        updates = {}
        stored_destination = str(flight_request.destination or "").strip().upper()
        if (
            stored_destination == legacy_destination
            and legacy_destination != expected_destination
        ):
            updates["destination"] = expected_destination
        if (
            flight_request.return_date == legacy_return_date
            and legacy_return_date != expected_return_date
        ):
            updates["return_date"] = expected_return_date

        if updates:
            flight_model.objects.using(database_alias).filter(
                pk=flight_request.pk
            ).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ("demo", "0012_profile_picture_storage"),
    ]

    operations = [
        migrations.RunPython(
            correct_flight_route_details,
            migrations.RunPython.noop,
        ),
    ]
