from django.db import migrations, models


def backfill_organization_join_codes(apps, schema_editor):
    Organization = apps.get_model("demo", "Organization")

    for organization in Organization.objects.filter(join_code__isnull=True):
        base_code = f"ORG{organization.id}"
        code = base_code
        suffix = 1
        while Organization.objects.filter(join_code=code).exclude(id=organization.id).exists():
            suffix += 1
            code = f"{base_code}{suffix}"
        organization.join_code = code
        organization.save(update_fields=["join_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("demo", "0008_flight_model_travel_agency"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="join_code",
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
        migrations.RunPython(backfill_organization_join_codes, migrations.RunPython.noop),
    ]
