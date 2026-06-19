from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_flight_role_links(apps, schema_editor):
    Staff = apps.get_model("demo", "Staff")
    Admin = apps.get_model("demo", "Admin")
    Flight = apps.get_model("demo", "Flight_model")

    for flight in Flight.objects.filter(user_id__isnull=False):
        update_fields = []
        staff = Staff.objects.filter(staff_id=flight.user_id).first()
        if staff and not flight.requested_by_staff_id:
            flight.requested_by_staff_id = staff.id
            update_fields.append("requested_by_staff")

        if staff and staff.organization_id and not flight.organization_id:
            flight.organization_id = staff.organization_id
            update_fields.append("organization")

        if flight.organization_id and not flight.assigned_admin_id:
            admin = Admin.objects.filter(
                organization_id=flight.organization_id,
                approval_status=True,
            ).first()
            if admin:
                flight.assigned_admin_id = admin.id
                update_fields.append("assigned_admin")

        if update_fields:
            flight.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("demo", "0004_localflightfare"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="ThriveAdmin",
            new_name="TravelAgency",
        ),
        migrations.AlterField(
            model_name="travelagency",
            name="admin",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="travel_agency_profile",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, unique=True)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "travel_agency",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="organizations",
                        to="demo.travelagency",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="admin",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="admins",
                to="demo.organization",
            ),
        ),
        migrations.AddField(
            model_name="staff",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="staff_members",
                to="demo.organization",
            ),
        ),
        migrations.AddField(
            model_name="flight_model",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="flight_requests",
                to="demo.organization",
            ),
        ),
        migrations.AddField(
            model_name="flight_model",
            name="requested_by_staff",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="flight_requests",
                to="demo.staff",
            ),
        ),
        migrations.AddField(
            model_name="flight_model",
            name="assigned_admin",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_flight_requests",
                to="demo.admin",
            ),
        ),
        migrations.AddField(
            model_name="flight_model",
            name="approved_by_admin",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_flight_requests",
                to="demo.admin",
            ),
        ),
        migrations.RunPython(backfill_flight_role_links, migrations.RunPython.noop),
    ]
