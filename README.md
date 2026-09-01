# Online Booking Tool

## Duffel flight search

Flight search and airport autocomplete use Duffel when these environment
variables are set:

```env
USE_LIVE_FLIGHT_API=True
FLIGHT_SEARCH_PROVIDER=duffel
DUFFEL_ACCESS_TOKEN=duffel_test_your_token_here
DUFFEL_API_BASE_URL=https://api.duffel.com
DUFFEL_API_VERSION=v2
DUFFEL_SUPPLIER_TIMEOUT_MS=15000
FLIGHT_SEARCH_TIMEOUT_SECONDS=25
FLIGHT_SEARCH_CACHE_SECONDS=60
FLIGHT_SEARCH_RELAX_TLS_STRICT=False
ALLOW_DUFFEL_TEST_DATA=True
```

Set `ALLOW_DUFFEL_TEST_DATA=False` when deploying with a live Duffel token.
When Duffel is unreachable, the existing local fare catalogue is used as a
fallback. A successful Duffel response is always authoritative, so local fares
are not mixed into live results—even when Duffel returns no offers.

The integration covers one-way, return, and multi-city offer searches plus
Duffel place suggestions. The existing corporate approval workflow is retained.
Creating paid Duffel orders is intentionally not enabled because the application
does not yet collect the passenger identity, document, and payment details that
Duffel requires for ticketing.

## Hotel search providers

Set the hotel provider independently from flight search:

```env
USE_LIVE_HOTEL_API=True
HOTEL_SEARCH_PROVIDER=local
MIN_HOTEL_RESULTS=12
```

`HOTEL_SEARCH_PROVIDER=local` uses the standalone hotel catalogue immediately.
Use `HOTEL_SEARCH_PROVIDER=amadeus` to try live Amadeus inventory first. Provider
errors, empty inventory, and unusable live records automatically fall back to
the standalone catalogue.
