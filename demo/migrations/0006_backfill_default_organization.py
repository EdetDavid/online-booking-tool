from django.db import migrations, models
import django.db.models.deletion


def backfill_default_organization(apps, schema_editor):
    Organization = apps.get_model("demo", "Organization")
    Admin = apps.get_model("demo", "Admin")
    Staff = apps.get_model("demo", "Staff")
    Flight = apps.get_model("demo", "Flight_model")

    organization, _ = Organization.objects.get_or_create(name="Default Organization")

    Admin.objects.filter(organization__isnull=True).update(organization=organization)
    Staff.objects.filter(organization__isnull=True).update(organization=organization)

    default_admin = Admin.objects.filter(
        organization=organization,
        approval_status=True,
    ).first()

    for flight in Flight.objects.filter(organization__isnull=True):
        if flight.requested_by_staff_id:
            staff = Staff.objects.filter(id=flight.requested_by_staff_id).first()
            if staff and staff.organization_id:
                flight.organization_id = staff.organization_id
        if not flight.organization_id:
            flight.organization = organization

        if default_admin and not flight.assigned_admin_id:
            flight.assigned_admin = default_admin

        update_fields = ["organization"]
        if default_admin:
            update_fields.append("assigned_admin")
        flight.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("demo", "0005_organization_travelagency_flight_roles"),
    ]

    operations = [
        migrations.RunPython(backfill_default_organization, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="admin",
            name="organization",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="admins",
                to="demo.organization",
            ),
        ),
        migrations.AlterField(
            model_name="staff",
            name="organization",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="staff_members",
                to="demo.organization",
            ),
        ),
    ]
