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
- An S3-compatible bucket stores uploaded profile images.

SQLite and local uploaded files are not suitable for Vercel Functions. The
runtime filesystem is ephemeral/read-only outside its temporary directory, and
instances do not share local state.

### 1. Rotate and remove historical secrets

Do this before connecting the repository to Vercel. Treat every credential
that has ever appeared in `.env`, Django settings, `db.sqlite3`, uploaded media,
terminal output, or Git history as compromised:

1. Revoke and reissue the Django secret, database credentials, AWS/S3 and SES
   keys, Duffel and Amadeus keys, Brevo key, and any other provider credential.
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

### 3. Provision S3-compatible media storage

Create a private bucket and a least-privilege credential that can read, write,
and delete objects only in that bucket. Prefer the storage-specific credential
names below so email/SES credentials can remain separate:

```env
USE_S3_STORAGE=True
AWS_STORAGE_BUCKET_NAME=
AWS_STORAGE_ACCESS_KEY_ID=
AWS_STORAGE_SECRET_ACCESS_KEY=
AWS_S3_REGION_NAME=
AWS_S3_ENDPOINT_URL=
AWS_S3_CUSTOM_DOMAIN=
AWS_QUERYSTRING_AUTH=True
AWS_S3_FILE_OVERWRITE=False
```

For AWS S3, `AWS_S3_ENDPOINT_URL` is normally omitted. For Cloudflare R2 or
another compatible service, set the provider endpoint and its required region
or addressing style. `AWS_S3_CUSTOM_DOMAIN` is optional and should be a host
name without `https://`. Keep signed URLs enabled for a private bucket; disable
them only after intentionally configuring public/CDN access.

`AWS_STORAGE_SESSION_TOKEN`, `AWS_DEFAULT_ACL`, and
`AWS_S3_ADDRESSING_STYLE` are also supported when required by the provider.
Supplying `AWS_STORAGE_BUCKET_NAME` automatically enables S3 storage. Production
startup fails if persistent media storage is missing rather than silently
writing uploads to an ephemeral filesystem.

Use a separate bucket or at least an isolated prefix/account for Preview
deployments.

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
AWS_STORAGE_BUCKET_NAME=
AWS_STORAGE_ACCESS_KEY_ID=
AWS_STORAGE_SECRET_ACCESS_KEY=
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

Configure at least one email backend before testing approval notifications.
The default Brevo backend uses `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, and
optionally `BREVO_SENDER_NAME`. If SES is the fallback, configure its region and
credentials separately. Provider credentials for live flight/hotel search are
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
