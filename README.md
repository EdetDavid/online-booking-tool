# Online Booking Tool

A Django booking application with flight and hotel search, corporate approval,
booking carts, email notifications, and profile images.

## Local setup

Use a supported Python version and create a virtual environment, then run:

```console
python -m pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py runserver
```

Fill in the values required for the providers you enable. The default local
configuration uses SQLite and filesystem media; production deliberately does
not.

Run the checks before committing:

```console
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Flight search

Flight search and airport autocomplete use Duffel when these environment
variables are set:

```env
USE_LIVE_FLIGHT_API=True
FLIGHT_SEARCH_PROVIDER=duffel
DUFFEL_ACCESS_TOKEN=
DUFFEL_API_BASE_URL=https://api.duffel.com
DUFFEL_API_VERSION=v2
DUFFEL_SUPPLIER_TIMEOUT_MS=15000
FLIGHT_SEARCH_TIMEOUT_SECONDS=25
FLIGHT_SEARCH_CACHE_SECONDS=60
FLIGHT_SEARCH_RELAX_TLS_STRICT=False
ALLOW_DUFFEL_TEST_DATA=False
```

Keep `ALLOW_DUFFEL_TEST_DATA=False` when using a live Duffel token. When Duffel
is unreachable, the local fare catalogue is used as a fallback. A successful
Duffel response is authoritative, so local fares are not mixed into live
results, even when Duffel returns no offers.

The integration covers one-way, return, and multi-city offer searches plus
Duffel place suggestions. The corporate approval workflow is retained. Creating
paid Duffel orders is intentionally not enabled because the application does
not yet collect the passenger identity, document, and payment details required
for ticketing.

## Hotel search

Configure hotels independently from flights:

```env
USE_LIVE_HOTEL_API=True
HOTEL_SEARCH_PROVIDER=local
MIN_HOTEL_RESULTS=12
```

`HOTEL_SEARCH_PROVIDER=local` uses the standalone hotel catalogue immediately.
Use `HOTEL_SEARCH_PROVIDER=amadeus` to try live Amadeus inventory first.
Provider errors, empty inventory, and unusable live records automatically fall
back to the standalone catalogue.

## Deploy to Vercel

Production uses three independent services:

- Vercel runs Django and serves collected static assets through WhiteNoise.
- A managed PostgreSQL service stores users, sessions, and booking data.
- A Backblaze B2 bucket stores uploaded profile images.

SQLite and local uploaded files are not suitable for Vercel Functions. The
runtime filesystem is ephemeral/read-only outside its temporary directory, and
instances do not share local state.

### 1. Rotate and remove historical secrets

Do this before connecting the repository to Vercel. Treat every credential
that has ever appeared in `.env`, Django settings, `db.sqlite3`, uploaded media,
terminal output, or Git history as compromised:

1. Revoke and reissue the Django secret, database credentials, Backblaze B2 and
   AWS/SES keys, Duffel and Amadeus keys, Brevo key, and any other provider
   credential.
2. Put only the new values in Vercel environment variables or a local ignored
   `.env`; never commit them.
3. Remove the currently tracked database and uploads while retaining local
   copies with `git rm --cached db.sqlite3` and
   `git rm -r --cached media`.
4. Rewrite history with a tool such as `git filter-repo` to remove historical
   `.env`, database, media, and settings secrets. Coordinate the rewrite before
   force-pushing because every collaborator must re-clone or carefully rebase.
5. Re-scan the complete Git history. History removal is not a substitute for
   credential rotation.

See GitHub's guidance on
[removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

### 2. Provision PostgreSQL

Create a managed PostgreSQL database in the same or a nearby region. A Vercel
Marketplace integration or any externally reachable PostgreSQL provider works.
Prefer the provider's pooled/serverless connection URL when it offers one.

Set these for Production in Vercel:

```env
DATABASE_URL=
DATABASE_CONN_MAX_AGE=60
DATABASE_CONN_HEALTH_CHECKS=True
DATABASE_SSL_REQUIRE=True
```

`DATABASE_URL` must start with `postgres://` or `postgresql://`. URL-encode
special characters in its username, password, and database name. Query options
such as `sslmode` and `channel_binding` are preserved. Follow the database
provider's pooling guidance; a transaction pooler may require
`DATABASE_CONN_MAX_AGE=0`.

Use a separate database for Preview deployments. Never point untrusted preview
branches at production customer data.

### 3. Provision Backblaze B2 media storage

Create a private [Backblaze B2 bucket](https://www.backblaze.com/docs/cloud-storage-buckets)
in a suitable region. Then create a manually generated, bucket-restricted
[application key](https://www.backblaze.com/docs/cloud-storage-s3-compatible-app-keys);
the B2 master application key is not supported by the S3-compatible API. The
application needs the `listFiles`, `readFiles`, `writeFiles`, and `deleteFiles`
capabilities. A bucket-restricted key may also need `listAllBucketNames` so the
SDK can perform `List Buckets` or `Head Bucket` requests.

Set these environment variables in Vercel:

```env
USE_B2_STORAGE=True
B2_BUCKET_NAME=
B2_APPLICATION_KEY_ID=
B2_APPLICATION_KEY=
B2_REGION=us-east-005
B2_ENDPOINT_URL=
B2_MEDIA_LOCATION=media
B2_QUERYSTRING_AUTH=True
B2_QUERYSTRING_EXPIRE=3600
B2_FILE_OVERWRITE=False
B2_ADDRESSING_STYLE=path
B2_CUSTOM_DOMAIN=
```

`B2_APPLICATION_KEY_ID` is the S3 access-key equivalent and
`B2_APPLICATION_KEY` is the secret-key equivalent. When `B2_ENDPOINT_URL` is
blank, the application derives `https://s3.<B2_REGION>.backblazeb2.com`; if set,
it must match that HTTPS endpoint exactly. The project uses django-storages'
S3-compatible client, but the endpoint is locked to Backblaze and does not send
media to AWS. See the official
[django-storages Backblaze guide](https://django-storages.readthedocs.io/en/1.14.6/backends/s3_compatible/backblaze-B2.html).

Backblaze applies access control at bucket level, so the application never sets
per-object ACLs. The recommended private-bucket configuration keeps
`B2_QUERYSTRING_AUTH=True` and generates expiring signed URLs. Only set it to
`False` and configure `B2_CUSTOM_DOMAIN` after intentionally making the bucket
public and routing that host through a compatible CDN.

Set `USE_B2_STORAGE=True` to enable B2 storage. Production startup fails if B2
storage is disabled or its required configuration is missing rather than
silently writing uploads to an ephemeral filesystem. Use a separate bucket or
at least an isolated prefix/application key for Preview deployments.

### 4. Configure Vercel environment variables

Start from [.env.example](.env.example), but enter real values only in Vercel's
encrypted environment-variable UI. At minimum, Production needs:

```env
DJANGO_ENV=production
DEBUG=False
SECRET_KEY=
DATABASE_URL=
ALLOWED_HOSTS=booking.example.com
CSRF_TRUSTED_ORIGINS=https://booking.example.com
USE_B2_STORAGE=True
B2_BUCKET_NAME=
B2_APPLICATION_KEY_ID=
B2_APPLICATION_KEY=
B2_REGION=
EMAIL_BACKEND=django_ses.SESBackend
EMAIL_HOST_USER=verified-sender@example.com
DEFAULT_FROM_EMAIL=verified-sender@example.com
SERVER_EMAIL=verified-sender@example.com
AWS_SES_ACCESS_KEY_ID=
AWS_SES_SECRET_ACCESS_KEY=
AWS_SES_REGION_NAME=eu-north-1
AWS_SES_REGION_ENDPOINT=email.eu-north-1.amazonaws.com
```

Generate `SECRET_KEY` with a cryptographically secure password generator or
Django's `get_random_secret_key()` and store the output directly in Vercel. Do
not paste it into a command, issue, chat, log, or committed file.

`ALLOWED_HOSTS` is a comma-separated list of host names without schemes or
paths. `CSRF_TRUSTED_ORIGINS` is a comma-separated list of full HTTPS origins.
Vercel supplies `VERCEL` and `VERCEL_URL`; the application automatically trusts
the assigned deployment host. Add every custom production domain explicitly.

Recommended production hardening values are:

```env
TRUST_X_FORWARDED_PROTO=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=3600
SECURE_HSTS_INCLUDE_SUBDOMAINS=False
SECURE_HSTS_PRELOAD=False
```

Increase HSTS to a long duration and opt into subdomains/preload only after
confirming that every affected host will remain HTTPS-only. Production mode
forces `DEBUG=False` even if it is accidentally configured otherwise.

Production uses [django-ses](https://github.com/django-ses/django-ses) and Amazon
SES by default. Use an SES-specific IAM key with permission to send email, set
`EMAIL_HOST_USER`, `DEFAULT_FROM_EMAIL`, and `SERVER_EMAIL` to a sender identity
verified in the configured SES region, and use `AWS_SES_SESSION_TOKEN` only for
temporary credentials. New SES accounts must leave the sandbox before sending
to arbitrary recipients. Brevo remains available as an explicit alternative by
setting `EMAIL_BACKEND=demo.brevo_email_backend.BrevoEmailBackend` and its
`BREVO_*` variables. Provider credentials for live flight/hotel search are
optional unless their corresponding live provider is enabled.

Set sensitive values independently for Production, Preview, and Development.
Do not expose production database, bucket, email, or travel-provider credentials
to Preview deployments.

### 5. Run database migrations separately

The Vercel build collects static assets but intentionally does not run
`makemigrations` or `migrate`. Concurrent and repeated serverless builds must
not modify the production schema.

Create and commit migrations during development. For each release, run the
following once from a trusted administrative environment that already has the
production environment variables securely loaded:

```console
python manage.py migrate --plan
python manage.py migrate --no-input
# or: sh migrate.sh
```

Take a provider snapshot/backup first. Prefer backward-compatible migrations,
run them before directing traffic to code that requires the new schema, and
have a tested rollback plan. Do not put `DATABASE_URL` directly on a command
line because shell history and process listings may expose it.

### 6. Validate and deploy

Run the release checks with production-shaped, non-production credentials:

```console
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py collectstatic --no-input --clear
```

Resolve every unexpected deploy-check warning. Then import the Git repository
into Vercel, add the environment variables, and deploy a Preview first. Verify:

- the home, login, flight, hotel, admin, and travel-agency pages load;
- static CSS/JavaScript returns successful responses;
- registration/login persists across requests;
- an uploaded profile image remains available after a new deployment;
- emails and enabled search providers work without test data;
- health/error logs contain no credentials or database URLs.

After the smoke test, run the production migration once and promote/deploy to
Production. Refer to Vercel's
[Django deployment guide](https://vercel.com/docs/frameworks/full-stack/django)
for project import and domain setup.
