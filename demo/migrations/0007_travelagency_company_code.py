from django.db import migrations, models


def seed_default_company_code(apps, schema_editor):
    TravelAgency = apps.get_model("demo", "TravelAgency")
    default_code = "OBT1234"

    if TravelAgency.objects.filter(company_code=default_code).exists():
        return

    agency = TravelAgency.objects.filter(
        approval_status=True,
        company_code__isnull=True,
    ).first()
    if agency:
        agency.company_code = default_code
        agency.save(update_fields=["company_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("demo", "0006_backfill_default_organization"),
    ]

    operations = [
        migrations.AddField(
            model_name="travelagency",
            name="company_code",
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
        migrations.RunPython(seed_default_company_code, migrations.RunPython.noop),
    ]
