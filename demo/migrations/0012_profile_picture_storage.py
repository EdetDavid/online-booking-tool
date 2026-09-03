from django.db import migrations, models


def clear_legacy_default_picture(apps, schema_editor):
    profile = apps.get_model('demo', 'Profile')
    profile.objects.filter(profile_picture='default.png').update(
        profile_picture=''
    )


class Migration(migrations.Migration):

    dependencies = [
        ('demo', '0011_travelagency_exchange_rate'),
    ]

    operations = [
        migrations.RunPython(
            clear_legacy_default_picture,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='profile',
            name='profile_picture',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='profile_pictures/',
            ),
        ),
    ]
