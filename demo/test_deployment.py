import json
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from online_booking_tool.settings import database_config_from_url, parse_csv


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
            "AWS_STORAGE_ACCESS_KEY_ID",
            "AWS_STORAGE_SECRET_ACCESS_KEY",
            "AWS_STORAGE_SESSION_TOKEN",
            "DUFFEL_ACCESS_TOKEN",
            "AMADEUS_CLIENT_ID",
            "AMADEUS_CLIENT_SECRET",
            "BREVO_API_KEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
        )
        for key in sensitive_keys:
            with self.subTest(key=key):
                self.assertIn(key, env_values)
                self.assertEqual(env_values[key], "")

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
