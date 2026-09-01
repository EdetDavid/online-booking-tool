from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("demo", "0009_organization_join_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="flight_model",
            name="booking_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="flight_model",
            name="booking_payload",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
