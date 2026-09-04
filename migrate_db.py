#!/usr/bin/env python
"""
Migrate data from SQLite to PostgreSQL (Neon).
This script uses Django's JSON serialization for safe data migration.
"""

import os
import sys
import django
import json
from pathlib import Path

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "online_booking_tool.settings")
sys.path.insert(0, str(Path(__file__).parent))
django.setup()

from django.core.management import call_command
from django.db import connections

def migrate_database():
    """Migrate data from SQLite to PostgreSQL."""
    
    print("=" * 60)
    print("DATABASE MIGRATION: SQLite → PostgreSQL (Neon)")
    print("=" * 60)
    
    # Check if DATABASE_URL is set
    if not os.environ.get("DATABASE_URL"):
        print("\n❌ ERROR: DATABASE_URL environment variable not set!")
        print("Please set DATABASE_URL in your .env file with your Neon database URL.")
        sys.exit(1)
    
    print("\n1️⃣  Dumping data from SQLite...")
    try:
        # Dump all data from SQLite to JSON
        with open("sqlite_dump.json", "w") as f:
            call_command("dumpdata", stdout=f, indent=2)
        print("✓ Data dumped to sqlite_dump.json")
    except Exception as e:
        print(f"❌ Error dumping SQLite data: {e}")
        sys.exit(1)
    
    print("\n2️⃣  Running migrations on PostgreSQL...")
    try:
        # Apply all migrations to PostgreSQL database
        call_command("migrate")
        print("✓ Migrations applied successfully")
    except Exception as e:
        print(f"❌ Error running migrations: {e}")
        sys.exit(1)
    
    print("\n3️⃣  Loading data into PostgreSQL...")
    try:
        # Load data from JSON dump into PostgreSQL
        call_command("loaddata", "sqlite_dump.json")
        print("✓ Data loaded successfully")
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        print("\nNote: Some data might not load if there are constraint conflicts.")
        print("You may need to manually resolve conflicts.")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✅ Migration completed successfully!")
    print("=" * 60)
    print("\nYou can now:")
    print("  1. Verify data in Neon: psql your_database_url")
    print("  2. Remove sqlite_dump.json: rm sqlite_dump.json")
    print("  3. Keep db.sqlite3 as backup (or delete it)")

if __name__ == "__main__":
    migrate_database()
