# LinguaFusion cloud pilot — prepared, not deployed

This is a separate lightweight FastAPI service. It does not import the local
GPU engines, access PC databases, or change the running app/tunnel. The pilot
implements verified Firebase identity, an explicit owner allowlist and text
translation using the OpenAI Responses API. Cloud AI defaults to OFF.

## Hosting decision

### September 7: model choice and money tracking

The pilot now exposes a model picker and an owner access/budget form. Paid
choices: GPT-5.6 Luna, Terra, Sol; prices sourced from their official model pages
on 2026-09-07. Prices require review after2026-10-07, otherwise paid dispatch
fails closed. Local NLLB/Argos/Ollama entries are labelled no-API-fee / PC-only;
they cannot run from this pilot and are not silently substituted with paid AI.
Local hardware/electricity are not free. OmniRoute integration was requested
mid-task; exact official documentation URL is awaited. No OmniRoute requests,
keys, model claims or unverified free offerings have been added.

`GET /models` and `/usage` are authenticated. Client sends `model` and explicit
`paid_consent=true`; server validates against its catalog and owner-configured
`LF_CLOUD_ALLOWED_MODELS` (fallback: single LF_CLOUD_TRANSLATION_MODEL). Paid
AI remains OFF in the local launcher. Owner form can set
`monthly_budget_usd` (0–1000, at most2 decimals); default budget is ZERO.
Changing budget never enables models/provider credentials.

Money stored as integer micro-USD: request reservations, token-based estimated
costs, unresolved holds and remaining monthly allowance. Usage discounts cached
input; output tokens include billed reasoning tokens as reported by provider.
Fixed standard tier / no reasoning requested / no tools. Before dispatch,
atomically reserve a conservative UTF-8 byte-based input bound +2048 overhead,
1.25x input-rate allowance and2048 maximum output tokens. Missing or ambiguous
usage, timeouts, errors or process death keep the hold; no automatic refund.
Settlement is idempotent. Request count and money reservation share a transaction.

This is NOT a verified invoice or guaranteed account-wide spend cap. Tax,
hosting, external API usage, price drift and provider adjustments are excluded.
No provider billing reconciliation exists yet. New zero total means no recorded
paid use in this pilot, not zero account-wide costs. Existing monthly-request
limits, rate limits, revocation and managed-cloud-storage requirements remain.

Official prices: [Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
[Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra),
[Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol).

Recommended first host: a CPU container on Google Cloud Run, with Firebase
Authentication in the same project. Cloudflare can continue serving the PC
tunnel while the pilot uses its own service URL. Do not repoint the production
domain until mobile integration and PC-off tests pass.

Cloudflare Python Workers do support FastAPI, but their supported-package and
memory constraints are not a lift-and-shift environment for this repository's
Torch/CUDA, native OCR, and local speech models. A lightweight Worker rewrite
could serve an API-only subset; retaining Python in a container reduces that
rewrite and leaves room for document-processing dependencies later.

Cloud Run's filesystem is disposable: do not copy the production SQLite files
into the image or use it for persistent notes, permissions, quotas or jobs.
Persistent user data, temporary private object storage and durable task queues
remain the next stage. R2/D1 are options, not dependencies added by this pilot.

## What has been built

- Public `GET /health` reports minimal liveness.
- Bearer Firebase ID tokens are verified by the Admin SDK, including signature,
  project audience/issuer, expiry and revoked/disabled status. Emulator mode is
  refused. Only UIDs in `LF_CLOUD_ALLOWED_UIDS` can use protected endpoints.
- `GET /capabilities` reports the pilot's supported features honestly.
- `POST /translate` accepts the existing form fields `text`, `source_lang`,
  `target_lang`, and returns `ok` and `translated_text`. Supported languages:
  English, German, Spanish, Hindi, Arabic and Odia. This is protocol support,
  not yet a live quality evaluation of these languages.
- Fixed server-side provider URL; key/model cannot be chosen by the caller.
  No tools or arbitrary network destinations. Responses use `store: false`;
  this does not imply zero provider retention or on-device processing.
- 4,000 characters, 2,048 output tokens, 64 KiB request body, bounded body and
  provider deadlines, two active translations and ten attempts per user/minute.
- Errors and request logs omit credentials, prompts, translations, client IPs
  and query strings. Logs contain generated request IDs, route/status/duration.
- Container build uses an allowlisted build context and a non-root runtime.
  No production credentials, databases, models, recordings or backups are copied.

### Provider capabilities behind the managed policy (September 8)

`POST /api/translate`, `/api/pronounce`, `/api/transcribe` and `/api/ocr` expose
the tested OpenRouter, Groq and Google Vision adapters. Each one requires an
approved UID, `paid_consent` on every request, and an explicit owner opt-in in
`LF_CLOUD_PILOT_FEATURES` (comma-separated: `translate,pronounce,transcribe,ocr`).
That variable is EMPTY by default, so every capability ships OFF and
`GET /capabilities` reports it as unavailable. A capability is also hidden when
its credential is missing, so a client never offers a control that must fail.

Credentials come from `LF_OPENROUTER_KEY` and `LF_GROQ_KEY`; OCR uses ambient
Application Default Credentials and never a key file. `LF_CLOUD_TEST_BUDGET_DB`
points at the shared lifetime allowance and is refused on Cloud Run, where an
ephemeral SQLite file would re-grant the whole allowance on every cold start.

Every dispatch must clear two independent ledgers: the per-user managed policy
(monthly attempts and USD budget) first, then the shared lifetime allowance. The
order matters -- a per-user hold resets monthly, whereas a lifetime hold is
permanent, so the scarce one is risked last. A hold is settled to zero only when
this process knows nothing was dispatched. Any failure that may have reached a
provider keeps its hold and is never retried.

`/api/transcribe` and `/api/ocr` accept up to 4 MB; every other route keeps the
64 KiB text cap. The larger cap is granted per exact path, never by prefix.

The pronunciation guide is a reading aid, not a translation. The pilot page
shows the native text first and never replaces it, always displays the
approximate-pronunciation warning, and discards any guide that fails to echo
the submitted text, changes language, drops the approximate flag, or returns
non-Latin script. `backend/services/transliteration_service.py` is NOT a
substitute: its `to_roman()` deliberately returns an empty string for Hindi.

The production phone apps still use the existing PC pairing flow. A separate
`/pilot/` page now connects Firebase sign-in to this API on the same origin.
No fake sign-in or mock translation is enabled through runtime configuration;
simulated responses exist only in tests.

## Local checks

### Local persistent access controls (not managed cloud storage)

The local pilot launcher now configures `cloud_api/local-data/policy.sqlite3`
and the supplied pilot UID as owner. The database contains UIDs, access state,
monthly request allowances, attempted request counts and an owner-change audit
trail; no passwords, tokens, source text or translations. It is private local
data excluded from Git and the Docker build. Existing backup scripts target
backend/storage, so this new pilot database is NOT included in those backups.

Owner-only `GET /owner/users` lists up to 1,000 configured users and current UTC
month counts. `POST /owner/users/{uid}` accepts form fields `enabled` and
`monthly_limit` (0–10,000). The owner role is fixed in server configuration,
not editable by an API caller. A visible owner management screen is not built.
Initial approved users receive 100 attempted requests per UTC month; reseeding
does not reset changes or usage. Atomic reservations happen before provider
dispatch. Failed/time-out attempts are retained conservatively. Disabling an
account blocks subsequent checks/reservations, not an already-dispatched call.

AI now fails closed without a configured policy store. SQLite errors return503;
reapproval/restarts cannot replenish the allowance. This limits request counts,
NOT actual currency spend or all project-wide use. Quota exhaustion is reported
by the API; the existing page still uses a generic429 message, pending UI work.

Cloud Run rejects this local SQLite configuration explicitly. Implement and
test a managed transactional store before hosted AI can be enabled. No cloud
database, IAM grant or paid resource was provisioned by this change.

The owner supplied the registered Firebase web configuration, saved in
`web/firebase-config.mjs`. `web/cloud-auth.mjs` is a lazy-loaded
sign-in adapter used by the separate pilot page and included in the container.
It uses Firebase SDK 12.18.0 browser modules for this prototype;
bundle the SDK for production. Session-only login is the default, with explicit
remember-me support. Firebase manages token persistence/refresh; the adapter
does not store passwords or log credentials. Backend approval is still required
after authentication. Fourteen Node checks cover the adapter and API client:

```powershell
node --test cloud_api/web/cloud-auth.test.mjs cloud_api/web/cloud-client.test.mjs cloud_api/web/pronunciation.test.mjs
```

Pass the test files explicitly. `node --test <directory>` fails on Windows here.


Browser checks verified real CDN loading, required inputs, recovery from a
synthetic rejected login, and the signed-out phone-sized layout. Successful
owner login, restored browser sessions, signed-in visual states and native
webviews still need real testing. API calls are restricted to fixed same-origin
routes with redirects refused, deadlines and cancellation on account changes.
Logout clears page text and late API responses are discarded.

Run `scripts/start_cloud_pilot.ps1` and open `http://127.0.0.1:8081/pilot/` on
the PC for private sign-in testing. This loopback-only launcher always disables
paid AI. It sets project/approved UID but does not provision Google Application
Default Credentials: backend approval checks return unavailable until ADC with
appropriate Firebase permissions is configured. Never download private keys
just to bypass that setup. No production domain or phone package was changed.
See [Firebase persistence](https://firebase.google.com/docs/auth/web/auth-state-persistence)
and [password sign-in](https://firebase.google.com/docs/auth/web/password-auth).

An isolated `.venv-cloud` is available on the development PC:

```powershell
.\.venv-cloud\Scripts\python.exe -m pytest .\cloud_api\test_cloud_api.py -q
.\.venv-cloud\Scripts\python.exe -m uvicorn cloud_api.app:app --host 127.0.0.1 --port 8081 --no-access-log --no-proxy-headers
```

Without configured Firebase and provider credentials, protected functionality
fails closed. No real AI calls were used in tests. Test injection is programmatic,
not an environment-variable authentication bypass.

Docker build command, once Docker is available:

```powershell
docker build -f cloud_api/Dockerfile -t linguafusion-cloud-pilot .
```

Docker is not installed on this development machine, so the image has not yet
been built/run. Python tests run on Windows/Python 3.10; the image targets Linux/
Python 3.11. Verify it in Cloud Build or a Docker-enabled environment before
deployment. The YAML is a review template, not an applied configuration.

## Owner setup and deployment gate

Project created by the owner: `linguafusion-f24fe` (Spark plan as shown in the
owner's console). Its public project ID is recorded in the configuration
templates; this does not deploy a service or authenticate the local backend.

Next console step: open Security > Authentication, select Get started if shown,
then Sign-in method > Email/Password. Enable the password provider and save;
email-link sign-in is not needed for this initial pilot. This is the proposed
first test sign-in method, not a change already made in the Firebase console.
Do not share passwords, ID tokens, or service-account keys in chat.
After enabling it, create a dedicated pilot test user in Authentication > Users;
its UID can then be explicitly approved on the backend. Creating an account
alone does not grant API access. Client sign-in integration is still pending.

1. Create a Firebase project in https://console.firebase.google.com/ (Analytics
   is optional). Record Project settings > General > Project ID. This also
   creates the Google Cloud project. No billing is needed just for this step.
2. Configure a sign-in method and register pilot web/Android/iOS clients later.
   Record the approved users' Firebase UIDs; default allowlist is empty.
3. Before Cloud Run deployment, review/approve billing, region, API model and
   provider data handling. Hosting/build/registry/logging/secrets and model
   usage are separate cost sources; no fixed monthly bill is promised.
4. Use a dedicated least-privilege runtime service account and Application
   Default Credentials. Give it permission to check Firebase user status and
   read only the relevant Secret Manager secret. Do not download or embed a
   service-account private key in the image or phone apps.
5. Build and test the container; fill `cloud-run.example.yaml`, initially with
   AI disabled and only the owner's supplied test UID approved. Cloud Run's HTTP invocation policy must
   permit the phone clients while the application enforces Firebase identity.
   Review that boundary before enabling public invocation.
6. Configure a versioned OPENAI_API_KEY secret, approved model and origins.
   Add durable usage quotas and a spending-control plan before enabling AI for
   friends. The pilot limiter resets at restart and is per instance; max-scale
   and budget alerts are NOT hard monthly spend caps. Leave AI off until this
   is addressed. Avoid public model-selection controls.
7. Run actual Firebase sign-in/revocation and one approved provider request;
   then implement phone cloud mode and an explicit cloud-processing disclosure.
   Only after speech/data integration, test with the PC off and begin rollout.

No paid resources, project, DNS change, API key or permission grant was created
by this implementation. Do not paste private keys into chat; configure secrets
through the provider console or an approved local credential mechanism.

## Official references checked September 7, 2026

- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
- [Python Workers packages](https://developers.cloudflare.com/workers/languages/python/packages/)
- [Cloud Run architecture](https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Cloud Run secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Firebase project relationship](https://firebase.google.com/docs/projects/learn-more)
- [Firebase token verification](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
- [Firebase revocation checks](https://firebase.google.com/docs/auth/admin/manage-sessions)
- [OpenAI text generation](https://developers.openai.com/api/docs/guides/text)
- [Responses request controls](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
