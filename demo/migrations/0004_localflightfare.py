from datetime import time
from decimal import Decimal

from django.db import migrations, models


def seed_local_fares(apps, schema_editor):
    LocalFlightFare = apps.get_model('demo', 'LocalFlightFare')
    fares = [
        ('LOS', 'ABV', 'P4', 'Air Peace', 'ECONOMY', '145000.00', time(7, 15), time(8, 35), None, None, '', 'PT1H20M', '', 18),
        ('LOS', 'ABV', 'Q9', 'Green Africa', 'ECONOMY', '118000.00', time(11, 10), time(12, 25), None, None, '', 'PT1H15M', '', 12),
        ('LOS', 'ABV', 'P4', 'Air Peace', 'BUSINESS', '310000.00', time(16, 20), time(17, 40), None, None, '', 'PT1H20M', '', 6),
        ('LOS', 'PHC', 'P4', 'Air Peace', 'ECONOMY', '132000.00', time(8, 45), time(9, 55), None, None, '', 'PT1H10M', '', 15),
        ('PHC', 'LOS', 'P4', 'Air Peace', 'ECONOMY', '128000.00', time(10, 40), time(11, 50), None, None, '', 'PT1H10M', '', 15),
        ('ABV', 'LOS', 'Q9', 'Green Africa', 'ECONOMY', '121000.00', time(9, 20), time(10, 40), None, None, '', 'PT1H20M', '', 16),
        ('LOS', 'ACC', 'AW', 'Africa World', 'ECONOMY', '285000.00', time(6, 50), time(7, 55), time(17, 45), time(18, 50), '', 'PT1H05M', 'PT1H05M', 9),
        ('LOS', 'ACC', 'P4', 'Air Peace', 'BUSINESS', '545000.00', time(13, 30), time(14, 45), time(19, 30), time(20, 45), '', 'PT1H15M', 'PT1H15M', 5),
        ('LOS', 'DXB', 'EK', 'Emirates', 'ECONOMY', '985000.00', time(18, 15), time(5, 45), time(9, 30), time(15, 55), '', 'PT7H30M', 'PT7H25M', 9),
        ('LOS', 'LHR', 'BA', 'British Airways', 'ECONOMY', '1250000.00', time(22, 50), time(5, 50), time(11, 15), time(18, 30), '', 'PT6H50M', 'PT6H45M', 9),
        ('LOS', 'JFK', 'DL', 'Delta', 'ECONOMY', '1680000.00', time(12, 25), time(19, 5), time(22, 10), time(10, 15), '', 'PT11H40M', 'PT10H55M', 8),
        ('ABV', 'DXB', 'QR', 'Qatar Airways', 'ECONOMY', '1110000.00', time(13, 35), time(2, 5), time(5, 20), time(12, 10), 'DOH', 'PT9H30M', 'PT9H50M', 7),
    ]

    for fare in fares:
        LocalFlightFare.objects.get_or_create(
            origin=fare[0],
            destination=fare[1],
            airline_code=fare[2],
            cabin=fare[4],
            departure_time=fare[6],
            defaults={
                'airline_name': fare[3],
                'base_price_naira': Decimal(fare[5]),
                'arrival_time': fare[7],
                'return_departure_time': fare[8],
                'return_arrival_time': fare[9],
                'stop_airport': fare[10],
                'flight_duration': fare[11],
                'return_duration': fare[12],
                'seats_available': fare[13],
                'active': True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('demo', '0003_auto_20241029_1159'),
    ]

    operations = [
        migrations.CreateModel(
            name='LocalFlightFare',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('origin', models.CharField(max_length=3)),
                ('destination', models.CharField(max_length=3)),
                ('airline_code', models.CharField(default='B6', max_length=3)),
                ('airline_name', models.CharField(default='JetBlue', max_length=100)),
                ('cabin', models.CharField(choices=[('ECONOMY', 'Economy'), ('PREMIUM_ECONOMY', 'Premium Economy'), ('BUSINESS', 'Business'), ('FIRST', 'First')], default='ECONOMY', max_length=20)),
                ('base_price_naira', models.DecimalField(decimal_places=2, max_digits=12)),
                ('departure_time', models.TimeField()),
                ('arrival_time', models.TimeField()),
                ('return_departure_time', models.TimeField(blank=True, null=True)),
                ('return_arrival_time', models.TimeField(blank=True, null=True)),
                ('stop_airport', models.CharField(blank=True, default='', max_length=3)),
                ('flight_duration', models.CharField(default='PT1H15M', max_length=20)),
                ('return_duration', models.CharField(blank=True, default='', max_length=20)),
                ('seats_available', models.PositiveIntegerField(default=9)),
                ('active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['origin', 'destination', 'base_price_naira'],
            },
        ),
        migrations.AddIndex(
            model_name='localflightfare',
            index=models.Index(fields=['origin', 'destination', 'cabin', 'active'], name='demo_localf_origin_62574a_idx'),
        ),
        migrations.RunPython(seed_local_fares, migrations.RunPython.noop),
    ]
