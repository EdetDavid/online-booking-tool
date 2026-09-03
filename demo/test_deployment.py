import json
import os
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from storages.backends.s3 import S3Storage

from online_booking_tool.settings import (
    backblaze_storage_options,
    database_config_from_url,
    default_email_backend,
    parse_csv,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DatabaseUrlSettingsTests(SimpleTestCase):
    def test_postgres_url_is_decoded_and_query_options_are_preserved(self):
        config = database_config_from_url(
            "postgresql://test%40user:encoded%2Ftest-value@"
            "database.example:6543/booking%20test"
            "?sslmode=verify-full&channel_binding=require"
        )

        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "booking test")
        self.assertEqual(config["USER"], "test@user")
        self.assertEqual(config["PASSWORD"], "encoded/test-value")
        self.assertEqual(config["HOST"], "database.example")
        self.assertEqual(config["PORT"], "6543")
        self.assertEqual(
            config["OPTIONS"],
            {"sslmode": "verify-full", "channel_binding": "require"},
        )

    def test_postgres_alias_and_implicit_port_are_supported(self):
        config = database_config_from_url(
            "postgres://database.example/booking"
        )

        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["HOST"], "database.example")
        self.assertEqual(config["PORT"], "")

    def test_invalid_or_incomplete_database_urls_are_rejected(self):
        invalid_urls = (
            "sqlite:///db.sqlite3",
            "postgresql:///booking",
            "postgresql://database.example",
            "postgresql://database.example:not-a-port/booking",
        )

        for database_url in invalid_urls:
            with self.subTest(database_url=database_url):
                with self.assertRaises(ImproperlyConfigured):
                    database_config_from_url(database_url)

    def test_csv_configuration_ignores_empty_items_and_whitespace(self):
        self.assertEqual(
            parse_csv(" booking.example, ,api.example "),
            ["booking.example", "api.example"],
        )


class BackblazeStorageSettingsTests(SimpleTestCase):
    @staticmethod
    def build_options(**overrides):
        values = {
            "bucket_name": "booking-media",
            "application_key_id": "test-key-id",
            "application_key": "test-application-key",
            "region": "us-east-005",
        }
        values.update(overrides)
        return backblaze_storage_options(**values)

    def test_private_storage_is_locked_to_backblaze(self):
        options = self.build_options()

        self.assertEqual(options["bucket_name"], "booking-media")
        self.assertEqual(options["access_key"], "test-key-id")
        self.assertEqual(options["secret_key"], "test-application-key")
        self.assertIsNone(options["security_token"])
        self.assertIsNone(options["session_profile"])
        self.assertEqual(options["region_name"], "us-east-005")
        self.assertEqual(
            options["endpoint_url"],
            "https://s3.us-east-005.backblazeb2.com",
        )
        self.assertEqual(options["signature_version"], "s3v4")
        self.assertEqual(options["addressing_style"], "path")
        self.assertIsNone(options["default_acl"])
        self.assertTrue(options["querystring_auth"])
        self.assertEqual(options["querystring_expire"], 3600)
        self.assertFalse(options["file_overwrite"])

    def test_non_backblaze_or_wrong_region_endpoints_are_rejected(self):
        invalid_endpoints = (
            "http://s3.us-east-005.backblazeb2.com",
            "https://s3.us-east-005.amazonaws.com",
            "https://s3.us-west-004.backblazeb2.com",
            "https://s3.us-east-005.backblazeb2.com/bucket-name",
        )

        for endpoint_url in invalid_endpoints:
            with self.subTest(endpoint_url=endpoint_url):
                with self.assertRaises(ImproperlyConfigured):
                    self.build_options(endpoint_url=endpoint_url)

    def test_invalid_backblaze_regions_are_rejected(self):
        for region in ("-us-east-005", "us-east-005-", "us_east_005", "éu-001"):
            with self.subTest(region=region):
                with self.assertRaises(ImproperlyConfigured):
                    self.build_options(region=region)

    def test_all_backblaze_credentials_are_required(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "B2_APPLICATION_KEY_ID, B2_APPLICATION_KEY",
        ):
            self.build_options(application_key_id="", application_key="")

    def test_custom_domain_requires_unsigned_public_urls(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "B2_QUERYSTRING_AUTH=False",
        ):
            self.build_options(custom_domain="media.example.com")

        options = self.build_options(
            querystring_auth=False,
            custom_domain="https://media.example.com",
        )
        self.assertEqual(options["custom_domain"], "media.example.com")
        self.assertEqual(options["url_protocol"], "https:")

    def test_aws_email_session_state_is_not_inherited(self):
        with patch.dict(
            os.environ,
            {
                "AWS_SESSION_TOKEN": "ses-session-token",
                "AWS_S3_SESSION_PROFILE": "aws-profile",
            },
        ):
            storage = S3Storage(**self.build_options())

        self.assertIsNone(storage.security_token)
        self.assertIsNone(storage.session_profile)


class EmailBackendSettingsTests(SimpleTestCase):
    def test_ses_is_the_production_default(self):
        self.assertEqual(default_email_backend(True), "django_ses.SESBackend")

    def test_local_default_does_not_deliver_email(self):
        self.assertEqual(
            default_email_backend(False),
            "django.core.mail.backends.console.EmailBackend",
        )


class DeploymentArtifactTests(SimpleTestCase):
    def test_vercel_uses_django_framework_detection_without_schema_mutation(self):
        manifest_path = PROJECT_ROOT / "vercel.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        serialized_manifest = json.dumps(manifest).lower()

        self.assertEqual(manifest["framework"], "django")
        self.assertNotIn("makemigrations", serialized_manifest)
        self.assertNotIn("migrate", serialized_manifest)

    def test_migration_script_is_an_explicit_separate_step(self):
        migration_script = (PROJECT_ROOT / "migrate.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("set -eu", migration_script)
        self.assertIn("python manage.py migrate --no-input", migration_script)
        self.assertNotIn("makemigrations", migration_script)

    def test_example_environment_does_not_contain_secret_values(self):
        env_values = {}
        for raw_line in (PROJECT_ROOT / ".env.example").read_text(
            encoding="utf-8"
        ).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_values[key] = value

        sensitive_keys = (
            "SECRET_KEY",
            "DATABASE_URL",
            "B2_APPLICATION_KEY_ID",
            "B2_APPLICATION_KEY",
            "DUFFEL_ACCESS_TOKEN",
            "AMADEUS_CLIENT_ID",
            "AMADEUS_CLIENT_SECRET",
            "BREVO_API_KEY",
            "AWS_SES_ACCESS_KEY_ID",
            "AWS_SES_SECRET_ACCESS_KEY",
            "AWS_SES_SESSION_TOKEN",
        )
        for key in sensitive_keys:
            with self.subTest(key=key):
                self.assertIn(key, env_values)
                self.assertEqual(env_values[key], "")

        for obsolete_key in (
            "USE_S3_STORAGE",
            "AWS_STORAGE_BUCKET_NAME",
            "AWS_STORAGE_ACCESS_KEY_ID",
            "AWS_STORAGE_SECRET_ACCESS_KEY",
            "AWS_STORAGE_SESSION_TOKEN",
            "AWS_MEDIA_LOCATION",
            "AWS_S3_REGION_NAME",
            "AWS_S3_ENDPOINT_URL",
            "AWS_S3_CUSTOM_DOMAIN",
            "AWS_S3_URL_PROTOCOL",
            "AWS_QUERYSTRING_AUTH",
            "AWS_S3_FILE_OVERWRITE",
            "AWS_DEFAULT_ACL",
            "AWS_S3_ADDRESSING_STYLE",
        ):
            with self.subTest(obsolete_key=obsolete_key):
                self.assertNotIn(obsolete_key, env_values)

    def test_local_state_is_excluded_from_git_and_vercel(self):
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        vercelignore = (PROJECT_ROOT / ".vercelignore").read_text(
            encoding="utf-8"
        )

        for ignored_path in (".env", "db.sqlite3", "media/"):
            with self.subTest(file=".gitignore", path=ignored_path):
                self.assertIn(ignored_path, gitignore.splitlines())
            with self.subTest(file=".vercelignore", path=ignored_path):
                self.assertIn(ignored_path, vercelignore.splitlines())
