from django.db import migrations, models
import django.db.models.deletion


def backfill_flight_travel_agencies(apps, schema_editor):
    Flight = apps.get_model("demo", "Flight_model")

    for flight in Flight.objects.select_related("organization").filter(
        travel_agency__isnull=True,
        organization__travel_agency__isnull=False,
    ):
        flight.travel_agency_id = flight.organization.travel_agency_id
        flight.save(update_fields=["travel_agency"])


class Migration(migrations.Migration):

    dependencies = [
        ("demo", "0007_travelagency_company_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="flight_model",
            name="travel_agency",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="flight_requests",
                to="demo.travelagency",
            ),
        ),
        migrations.RunPython(backfill_flight_travel_agencies, migrations.RunPython.noop),
    ]
