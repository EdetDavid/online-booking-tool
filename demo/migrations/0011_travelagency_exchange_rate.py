from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("demo", "0010_flight_model_booking_lifecycle"),
    ]

    operations = [
        migrations.AddField(
            model_name="travelagency",
            name="exchange_rate",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("1600.0000"),
                max_digits=12,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.0001"))
                ],
                verbose_name="USD to NGN exchange rate",
            ),
        ),
    ]
