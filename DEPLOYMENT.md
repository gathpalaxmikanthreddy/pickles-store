# Production deployment checklist

The `Procfile` starts the app with `APP_ENV=production`. Production startup fails
if required credentials, PostgreSQL, or shared rate-limit storage are missing.
Do not use `.env.example` values as production credentials.

## Configure before deployment

Set these in the hosting provider's secret/environment settings:

- `SECRET_KEY`: at least 32 random characters. Generate a new value for each
  environment and keep it out of source control.
- `ADMIN_USERNAME` and `ADMIN_PASSWORD`: unique credentials; do not use
  `admin` or example values.
- `DATABASE_URL`: managed PostgreSQL connection string. Back up the database
  before deployment because the app applies its existing schema migrations at
  startup.
- `RATELIMIT_STORAGE_URI`: a shared Redis/Valkey connection URI using TLS
  (`rediss://`), not process-local memory storage.
- `TRUSTED_PROXY_HOPS`: the exact number of trusted reverse proxies in front
  of the application (commonly `1`). Set this only when the outer proxy
  replaces forwarded headers; never trust client-supplied forwarding headers.
- `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`: use test-mode keys for staging;
  configure live keys only after successful end-to-end payment verification.
- `TEXTBEE_API_KEY` and `TEXTBEE_DEVICE_ID`: provider credentials for OTP
  delivery.

`SESSION_COOKIE_SECURE` is forced on in production. Terminate TLS at the
hosting edge and redirect all HTTP traffic to HTTPS there; the app emits HSTS
for production responses. Keep `FLASK_DEBUG=0`. Configure the hosting proxy so client addresses are handled correctly for
IP-based rate limits; do not trust arbitrary forwarded headers from the
public internet.

## Release verification

1. Install the pinned packages from `requirements.txt` and run
   `python -m pip_audit -r requirements.txt`.
2. Run `python -m unittest discover -s tests -v`.
3. In a staging environment, verify registration and password-reset OTP
   delivery, customer/admin authorization, COD collection recording, and
   Razorpay test payments. Never perform payment tests with a live key or real
   customer.
4. Verify backups and restore procedures, monitor application/database/Redis
   health, and confirm there are no credentials or customer details in logs.
5. Before go-live, use a client-owned domain, HTTPS certificate, production
   database, Redis, payment keys, and SMS provider credentials.

Inline scripts are authorized with a per-response nonce, and inline event
handlers have been moved to external JavaScript. Inline styles remain allowed
for compatibility with existing page styling, so the policy is not yet fully
strict. The app does not enable cross-origin API access; keep browser requests
same-origin unless a documented integration requires a narrowly scoped CORS
policy.
