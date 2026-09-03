#!/usr/bin/env sh
set -eu

# Run this explicitly against the production database after deploying code.
python manage.py migrate --no-input
