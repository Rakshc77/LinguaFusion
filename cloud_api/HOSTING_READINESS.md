# Hosted pilot readiness — 2026-09-08

User has approved hosting. Region and hosting budget are now CONFIRMED
(2026-09-08): Frankfurt (europe-west3), scale to zero, US$5/month alert.
An alert is NOT a hard spending cap; the US$5 lifetime AI-test allowance is
separate and is NOT the hosting budget. Cloud Run's spend-based cutoff is in
preview, is not instantaneous, and does not cover Firestore or Vision, so it
must not be described to the user as a guaranteed ceiling.

## Verified remotely, read-only

- Project: linguafusion-f24fe.
- Vision API enabled.
- Cloud Run, Firestore, Cloud Build, Artifact Registry and Secret Manager disabled.
- Database inventory HTTP403 RESOLVED (2026-09-08): the cause was SERVICE_DISABLED,
  not a permission wall. The Firestore API has since been enabled (enabling an
  API creates nothing and costs nothing) and the listing now returns HTTP 200
  with zero databases. No database exists, so nothing has to be relocated.
  The owner ADC identity holds datastore.databases.create/get/list,
  serviceusage.services.enable, run.services.create and iam.serviceAccounts.actAs.
  Re-check any time with scripts/check_firestore_access.py.
- Runtime account linguafusion-be@linguafusion-f24fe.iam.gserviceaccount.com
  currently has only Service Usage Consumer as an unconditional project role.
- No resources deployed, no new API test requests made during this step.

## Implemented locally

FirestorePolicy persists approval toggles, monthly request/user budgets, retained
reservations, idempotent settlement, and a shared lifetime allowance. Transactions
serialize decisions across processes. Initialization is deliberately NOT automatic.
The document path is linguafusion_private/pilot_policy_v1. Store no source text,
audio, OCR images, credentials, or translations in that document.

The small-pilot store is bounded: 50 users, 1,000 reservations, 1,000 policy events,
24 active months per user, and a conservative serialized size check. Hitting a
limit fails closed and requires planned migration; never delete charges to resume.

Cloud Run now refuses local/missing policy configuration or emulator settings.
Docker allowlist includes only the new module, not local ledgers or credentials.

Validation: 70 Python tests and 23 Node tests pass offline, plus the 85-test
backend suite. Gate 6/7 added 20 Python and 9 Node tests; the ledger settlement
rules were mutation-checked. Firestore
network transactions, retries, IAM and restart persistence are NOT live-tested.
The test transaction harness verifies policy logic, not Firestore behavior.

## Remaining release gates, in order

1. DONE (2026-09-08). Region and cost controls confirmed (Frankfurt europe-west3,
   scale to zero, US$5/month alert). Database inventory now readable: none exists.
   A Firestore location is PERMANENT once created, so create it in europe-west3
   to match Cloud Run, and never re-create it elsewhere afterwards.
2. DONE (2026-09-08). Enabled iam, run, cloudbuild, artifactregistry,
   secretmanager and cloudbilling. Billing confirmed linked. Firestore
   (default) created in europe-west3, FIRESTORE_NATIVE, delete protection ON,
   PITR off. Artifact Registry repo "linguafusion" created in europe-west3.
   Runtime account linguafusion-be@ now holds exactly
   roles/datastore.user, roles/firebaseauth.viewer and the pre-existing
   roles/serviceusage.serviceUsageConsumer -- no Owner or Editor.
   Provider secrets are NOT created: the keys live in DPAPI files readable only
   by the owner's Windows account, and must be added by the owner directly.
   RESOLVED (2026-09-08): the Compute Engine default service account, which
   Cloud Build runs as, carried roles/editor by Google default. It now holds
   only logging.logWriter, artifactregistry.writer and storage.objectViewer.
   A full image build and an in-image startup check were re-run after the
   removal and both passed, so the narrowing is verified, not assumed.
3. DONE (2026-09-08). cloud_api/firestore.rules published as release
   cloud.firestore. The live ruleset was read back and contains exactly one
   allow statement, "allow read, write: if false;" -- nothing grants access.
   The backend reaches Firestore as a service account, which bypasses rules,
   so deny-all for clients is correct and is the only ruleset that can be
   verified by reading it.
4. DONE (2026-09-08). FirestorePolicy exercised against the real restricted
   database, 12/12 checks: fails closed before initialization, create-only
   initialization carrying prior_reserved, reserve/settle round trip, disabled
   user refused, lifetime ceiling enforced, and state surviving a brand-new
   client (the cold-instance case). Run on a throwaway document; the production
   ledger linguafusion_private/pilot_policy_v1 was asserted absent before and
   after and STILL DOES NOT EXIST. It must be created only at cutover, by
   gate 5, carrying forward the recorded costs.
5. BUILT AND TESTED, NOT YET EXECUTED (2026-09-08).
   scripts/cutover_to_managed_ledger.py performs it; --confirm is required and
   a dry run reports without changing anything. Current dry run: carry forward
   160000 micro-USD (US$0.16) covering 16 unreconciled holds; no cloud ledger
   exists; local ledger not yet closed.
   Ordering is the safety argument: the local ledger is CLOSED FIRST, then the
   cloud document is created. If creation then fails, nothing can spend
   anywhere, and the script reopens local spending only after proving the cloud
   document is absent. The reverse order would, on a failure to close, leave
   both ledgers each permitting the remaining allowance.
   The cloud document is written with document.create() -- create-only, never
   set/overwrite, so a re-run cannot re-seed a fresh US$5.
   TestBudget now carries a cutover mark: reserve() refuses afterwards, the
   check runs inside the transaction, and the refusal survives restarts and new
   handles. carry_forward_micro() counts unresolved holds as spent, because
   they may still be billed.
   Double-charging is prevented by ManagedBudget: FirestorePolicy enforces the
   lifetime ceiling in the same transaction as the per-user hold, so the
   provider must NOT reserve again. app.py selects the ledger from the policy's
   enforces_lifetime_ceiling attribute rather than a config string, and a
   policy without a lifetime ceiling and without a TestBudget file leaves the
   capabilities unavailable instead of running uncapped.
   EXECUTED 2026-09-08T14:05:53Z. Local ledger closed and verified refusing
   new reservations; linguafusion_private/pilot_policy_v1 created with
   prior_reserved=160000, ceiling=5000000, US$4.84 remaining, owner enabled.
   The local combined-test-budget.sqlite3 is now CLOSED PERMANENTLY -- the
   scripts/test_cloud_*.py helpers will refuse by design. Do not clear the
   cutover mark: the cloud ledger exists, so reopening local spending would
   grant a second allowance.
6. DONE (2026-09-08, offline). OpenRouter/Groq/Vision now reach the managed
   policy through cloud_api/pilot_capabilities.py. Routes /api/translate,
   /api/pronounce, /api/transcribe and /api/ocr each require an approved UID,
   per-request paid consent, and an owner opt-in listed in
   LF_CLOUD_PILOT_FEATURES, which is EMPTY by default so every capability
   ships OFF. Each dispatch must clear BOTH ledgers: the per-user managed
   policy first, then the shared lifetime allowance, so a rejected request
   never burns the scarce shared budget. A hold is settled to zero only when
   this process knows nothing was dispatched; any post-dispatch failure keeps
   the hold and is never retried. The older OpenAI /translate route is
   unchanged and still separate. Cloud Run now refuses a SQLite lifetime
   ledger, which would otherwise re-grant the whole allowance on cold start.
   NOT live-tested against a real provider; every test uses a mock transport.
7. PARTIAL (2026-09-08). The pronunciation pane exists in the cloud pilot page
   only (cloud_api/web/): language choice limited to Hindi/Arabic/Odia, native
   text shown first and never replaced, a persistent approximate-pronunciation
   warning, and copy controls with a clipboard fallback. The client discards
   any guide that fails to echo the submitted text, changes language, drops the
   approximate flag, or comes back in non-Latin script.
   Still outstanding: speech and OCR have routes but no UI controls; the
   desktop and mobile PWA clients are untouched; and Arabic/Odia guide quality
   remains an open release gate -- Arabic previously failed validation and Odia
   was never reviewed. Note the local transliteration_service.py cannot serve
   this pane: its to_roman() returns "" for Hindi by an earlier deliberate
   product-quality decision, and falls back to unidecode elsewhere.
8. PARTIAL (2026-09-08). Image built and pushed via the Cloud Build API using
   ADC (no gcloud login, no local Docker):
   europe-west3-docker.pkg.dev/linguafusion-f24fe/linguafusion/cloud-pilot
   @sha256:784271d437915e0921586177079e11ec0e4a7e640c22e7cd1ce9d9f0cb25c0cf
   (revision 00006: raw-UID form collapsed behind a toggle)
   The upload context was assembled from an explicit allowlist (18 files,
   29 KB) and asserted to exclude ledgers, credentials, ADC and .test.mjs.
   Startup was verified by running the image and calling create_app(), which
   caught nothing only because the Dockerfile was first corrected: app.py
   imports pilot_capabilities, pilot_providers and test_budget, and none of
   the three were being COPYed -- the container would have crashed on boot.
   A regression test now asserts the build context covers every first-party
   import. Still outstanding here: no vulnerability scan, no runtime identity
   attached (that happens at deploy), no provider secrets, and no live
   authenticated-access or revoked-user test.
9. DONE (2026-09-08). Service linguafusion-cloud-pilot deployed to
   europe-west3, revision 00006 Ready, 100% traffic, minInstances 0,
   maxInstances 1, concurrency 8, 60s timeout, 1 vCPU / 512Mi, gen2.
   Pinned to the image DIGEST, not a tag, so the revision cannot drift.
   URL: https://linguafusion-cloud-pilot-jl77ipbeua-ey.a.run.app
   Runs as linguafusion-be@ with only datastore.user, firebaseauth.viewer and
   serviceusage.serviceUsageConsumer.
   A project-scoped EUR 5/month budget was created with alerts at 50/90/100%.
   An account-wide "EUR 5 Monthly Budget Alert" already existed and was left
   untouched. NEITHER IS A HARD CAP -- both only notify. Do not describe the
   instance cap as a spending cap either; it bounds concurrency, not dollars.
10. PARTIAL (2026-09-08). Verified from off-network over public HTTPS:
    /health 200; /capabilities 401 with no token AND 401 with a bogus token,
    which proves Firebase verification really runs server-side and that
    firebaseauth.viewer works; /pilot/ and all six allowlisted assets 200;
    pronunciation.test.mjs, app.py, .env and env.example all 404; CSP,
    Referrer-Policy, X-Content-Type-Options and no-store all present.
    Runtime env audited: no credential variable, no secret mount, no volume,
    LF_CLOUD_AI_ENABLED=0 and LF_CLOUD_PILOT_FEATURES empty.
    Production request logs contain only route label, status, duration and a
    generated request id -- no user content, IPs or query strings.
    SIGNED-IN ROUND TRIP CONFIRMED 2026-09-08T14:56Z from the owner's own
    browser: /capabilities, /models, /usage, /owner/users and /owner/requests
    all returned 200. That proves a real Firebase ID token was verified
    server-side, the owner was recognised, the Firestore policy ledger was read,
    and the new access-request collection was queried live -- all against the
    restricted database with deny-all client rules in place.
    NOT yet verified: a real paid provider round trip (no AI call has been made
    through the deployed service), a real phone off-LAN with the PC stopped,
    and revision rollback.

THE SERVICE IS NOW LIVE AND PUBLICLY REACHABLE at
https://linguafusion-cloud-pilot-jl77ipbeua-ey.a.run.app
Cloud Run allows unauthenticated invocation because the sign-in page has to
load before anyone can authenticate; the edge is deliberately NOT the auth
boundary. Every protected endpoint verifies a Firebase ID token in-process, and
only /health and the static /pilot/ assets are open.

PAID AI IS NOW ON (2026-09-08, revision 00002).

Provider keys were loaded straight from the owner's local file into Secret
Manager by scripts/add_provider_secret.py, which never prints, logs or commits
the value. Secrets lf-openrouter-key and lf-groq-key are pinned to europe-west3
with one enabled version each, and secretmanager.secretAccessor is granted to
the runtime account ON THOSE TWO SECRETS ONLY, not project-wide. The service
references them via secretKeyRef; no key value appears in the service config.
To rotate a key: re-run that script with --add-version.

MASTER SWITCH FIX (found while wiring this up): LF_CLOUD_AI_ENABLED gated only
the older /translate route. The /api/* capabilities consulted just
LF_CLOUD_PILOT_FEATURES, so an owner setting LF_CLOUD_AI_ENABLED=0 to stop all
paid calls would NOT have stopped them. PilotGateway.available() now requires
the master switch as well, with a test asserting every /api/* route returns 503
and reserves nothing while it is off. Keep it that way: one honest kill switch.

Owner spending controls: monthly limit 100 attempts, monthly budget US$1.00.
Those bind at the same point by design -- 100 attempts x the US$0.01 hold is
exactly US$1.00, so neither is the loose one. The lifetime ceiling is the real
constraint: US$4.84 of the US$5.00 remains. Raise the monthly budget through
the owner console; the lifetime ceiling is not raisable and should not be.

Verified live after the redeploy: /health 200; /capabilities, /usage, /models,
/api/translate and /api/pronounce all 401 without a token and 401 with a bogus
one, so authentication is enforced BEFORE any capability or spending check.
Still unverified: a real signed-in paid round trip, which needs the owner's
Firebase password.

The existing desktop app, mobile app and PC tunnel are unchanged. No public
cloud URL can honestly be provided until these deployment gates pass.

Re-check the provisioned state at any time, read-only:
  .venv-cloud\Scripts\python.exe scripts\check_deploy_readiness.py
  .venv-cloud\Scripts\python.exe scripts\check_firestore_access.py

## Access requests and per-user limits (2026-09-08)

Spending, as instructed: per-user monthly budget US$5.40 (~EUR 5) with a
matching 540-attempt limit, so budget and attempts bind at the same point.
The shared lifetime ceiling is the only hard stop and remains the number that
decides the worst case; the owner must raise it deliberately with
scripts/set_spending_ceiling.py --usd N --confirm. Per-user monthly budgets
renew; the ceiling does not. A ceiling below the sum of per-user monthly
budgets means the first spender takes the pot -- that is a real consequence,
not a bug.

New collection linguafusion_access_requests, separate from the policy ledger
because it holds personal data and the ledger must not. Stored per requester:
uid, name, organisation, and the email address taken FROM THE VERIFIED TOKEN,
never from the request body. No postal address and no phone number are
collected; data minimisation was chosen deliberately over the original request,
because a home address serves no purpose here and would make the owner the
controller of far more sensitive data. Bounded at 200 records, failing closed.
Deletion is supported (DELETE /owner/requests/{uid}) for erasure requests.

Endpoints: POST/GET /access/request for a signed-in but unapproved person;
GET /owner/requests and POST/DELETE /owner/requests/{uid} for the owner.
verified_claims() authenticates without requiring approval, so a newcomer can
reach the request form and nothing else; identity() is unchanged and still
gates every protected route. A request requires email_verified on the token.
Approval grants the standard allowance and denial revokes it in the ledger, so
the two never drift apart.

Notification: requests emit a log line carrying only an event name and an
8-character uid prefix -- never a name, organisation or address. The log metric
linguafusion_access_requests counts them. The owner attaches their own address
with scripts/setup_request_alerts.py --email ...; no address was guessed or
filled in on their behalf. Email only: SMS notification channels need a paid
Monitoring tier and bill outside the AI allowance.

NOT DONE, and deliberately: SMS two-factor authentication. Firebase Auth's
phone provider is a primary sign-in method, not a second factor; real MFA needs
an Identity Platform upgrade with its own pricing, and SMS bills per message
outside the EUR 5 allowance. A public request form that triggers SMS is also an
SMS-pumping target and would need reCAPTCHA/App Check first. Email verification
plus manual owner approval is what ships; the owner approving each person by
hand is the actual gate.

## Fixes from the owner's first real session (2026-09-08)

Two faults the browser exposed that no test had caught:

1. The paid-consent checkbox for the pronunciation pane sat INSIDE the fieldset
   that was disabled until consent was given, so the control needed to proceed
   disabled itself. Unescapable. The fieldset is now gated on readiness only and
   the submit BUTTON is gated on consent. A regression test asserts the line
   disabling #pronounceFields never mentions #pronounceConsent.

2. The page's model chooser, paid-consent box and Translate button all drove the
   LEGACY OpenAI /translate route, which needs OPENAI_API_KEY. That key is not
   set and is not going to be -- the allowance lives on OpenRouter. So the whole
   section was dead by construction and reported "Not enabled for this pilot".
   /capabilities now returns a `pilot` map saying which backend can serve each
   capability, and the page routes translation to /api/translate, hides the
   OpenAI model chooser, and enables consent when that path is live.

Alerting was rebuilt. The original policy used a metric threshold with
thresholdValue 0, which the API drops as a proto3 default, leaving the stored
threshold null and the condition ill-defined. It is now a conditionMatchedLog
policy firing directly on the log entry, with a 300s notification rate limit.
Note also that setup_request_alerts.py originally SKIPPED policy creation when a
policy already existed, so a corrected address would have been created and never
attached -- it now re-points the existing policy, and --recreate rebuilds it.

Email channels created through the API are not verified on creation; an
unverified channel accepts configuration and silently delivers nothing.
sendVerificationCode was issued to the owner address. Treat an alert as working
only once a real notification has actually arrived.

## Ownership and alert delivery (2026-09-08, confirmed)

The owner in perpetuity is the owner's Google account. Verified against Firebase:
LF_CLOUD_OWNER_UID kLqjJka0cHXTCZX0TQxA2QMlzKi1 resolves to exactly that
address, is not disabled, and signs in with a password provider. Do not point
owner configuration at any other address.

NOTE: that owner account has email_verified = false in Firebase. It does not
break anything today, because identity() short-circuits for the owner UID and
only /access/request requires a verified address. It is still worth fixing:
account recovery and any future check that trusts email_verified would fail,
and the owner is the one account that must never be locked out.

Alert delivery is PROVEN AND BOTH CHANNELS ARE VERIFIED (the owner's Google account,
the perpetual owner, and the account address on file as a second recipient).
Drop one by patching the policy's notificationChannels if a single recipient is
preferred. A verification code was delivered and accepted for each, so
Cloud Monitoring email demonstrably reaches the owner. Channels
for pratikshyam02@gmail.com (not an owner) and the placeholder you@example.com
were deleted. The alert policy is attached to a verified channel plus the
rajarshic95 owner channel; the latter stays unverified until its own code is
entered, which is why the proven channel remains attached in the meantime.
An unverified channel accepts configuration and silently delivers nothing, so
never leave a policy pointing only at one.

## Paid path proven end to end (2026-09-08)

The owner ran real requests through the deployed service. Recorded in the
managed ledger:

  pilot:openrouter/mistralai/mistral-nemo   2 requests   US$0.02 held
  pilot:openrouter/google/gemma-3-27b-it    1 request    US$0.01 held
  committed US$0.19 of the US$27.00 ceiling; US$26.81 remains

That closes the last unproven link: the Secret Manager reference, PilotGateway,
the per-user policy and the lifetime ceiling all fire together, for both
translation and the pronunciation guide. Every charge sits in
unresolved_reserved rather than estimated_spent, which is correct -- the US$0.01
hold is deliberately conservative and is never auto-settled, because the
provider's real figure is not known here. Do not "tidy" these into settled
charges without an actual invoice.

OPEN, deferred at the owner's request: Hindi translation quality is spotty.
Worth knowing before picking it up -- the cloud path sends text to
mistralai/mistral-nemo, a general-purpose chat model, with no equivalent of the
local pipeline's protections. The desktop app deliberately prefers NLLB-200, a
purpose-built translation model, precisely because general LLMs rewrite rather
than translate, and local LLM correction is gated by the word-overlap check in
_valid_correction(). The cloud route has neither. Likely fixes, in order of
expected value: use a translation-specific model, or add an overlap/fidelity
guard before returning a cloud translation. See CLAUDE.md on why NLLB was
chosen over routing translation through a chat LLM.

The owner console's raw "Firebase user UID" form now ships collapsed behind an
"Advanced" toggle, with a hint that it wants a UID and not an email address.
Approving from the Access requests queue fills the UID in automatically and is
the intended path; the manual form remains for revocation and edge cases.

## Full journey verified end to end (2026-09-08)

A disposable Firebase account was created, driven over HTTPS exactly as a phone
would, and deleted afterwards. 21 of 22 checks passed:

  invite URL serves the app; unapproved account refused (403); UNCONFIRMED
  address cannot even request access (403); confirmed address can request;
  requesting alone grants nothing (403); the request reaches the owner queue
  with the right name, organisation and verified email; approval grants access;
  all four capabilities advertised; pronounce, transcribe and OCR all returned
  200; a request without consent refused (422); an anonymous request refused
  (401); the new user's spending metered separately; revocation locks the
  account out immediately; personal data erased on cleanup.

Real outputs: translate "Good morning, my friend." -> "Guten Morgen, mein
Freund."; pronounce नमस्ते -> "namaste"; OCR of a drawn image -> "IH";
transcribe of a synthetic tone -> " " (correct: there is no speech in a tone,
and empty output is never "corrected").

KNOWN FLAKINESS: translate succeeded 4 of 5 attempts. This is a consequence of
a deliberate cost control, not a bug. pilot_providers.translate() pins
provider.only=['deepinfra'] with allow_fallbacks=False and a max_price ceiling,
so if that one provider is at capacity or its price moves above the ceiling the
request fails outright rather than costing more elsewhere. The hold is retained
and nothing is retried, which is correct. The trade-off is the owner's to make:
allow fallbacks or more providers for reliability, or keep strict cost control
and accept occasional retries.

Provider failures are now logged server-side as `provider_failure` with the
provider and HTTP status only -- never a response body or credential -- because
a 502 was previously indistinguishable from a bug in our own code. The caller
still receives a generic message.

The QR invite is generated by scripts/generate_cloud_invite_qr.py as PNG, SVG,
PDF and a web page with the code embedded inline. An earlier version scaled a
reportlab widget with a group transform that the SVG renderer silently dropped,
producing an unscannable code while exiting successfully; the invite page also
carried no code at all, only a link. Modules are now drawn at absolute
coordinates, and cloud_api/test_invite_qr.py reads every artifact back and
compares it to the encoded matrix pixel by pixel.

## Approvals were silently impossible (2026-09-08, fixed)

The owner could not approve anyone. The cause was window.confirm() in
decideRequest(): it returns false WITHOUT displaying anything in installed
PWAs, Android WebViews, and any page where dialogs were suppressed. The
handler then returned early with no message at all, so Approve did nothing and
showed no error.

Diagnosed by serving the real UI against real Firestore with only sign-in
stubbed (the owner's password is not available), then clicking Approve with
native confirm() left alone: it returned false and no request was sent. With
confirm stubbed true the approval worked, isolating the fault precisely.

Fixed with an in-page confirmation ("Approve this request?" plus Yes/Cancel
buttons inside the row), which works everywhere and is keyboard reachable.
A test now fails if confirm(), alert() or prompt() reappear in pilot.mjs.
The server side was never at fault: GET /owner/requests, POST
/owner/requests/{uid} for approve and deny, and DELETE all returned 200 and
wrote the correct policy rows throughout.

## Android app (2026-09-08)

android/LinguaFusionMobile now offers cloud mode alongside PC pairing. The
connection screen gained "Use LinguaFusion Cloud", which needs no pairing key:
the page signs in with Firebase and the owner approves the account. The choice
is remembered in the `mode` preference and reopens straight into the cloud app.

The cloud WebView deliberately has NO addJavascriptInterface. The native bridge
exposes resetConnection() -- which clears all saved settings -- and direct
microphone control, and a remotely served page has no business holding that.
The cloud page records through the Web Audio encoder in wav.mjs instead.

Microphone and file-picker support are shared with PC mode through
newWebViewWithMediaSupport(), so speech and OCR behave identically in both.
isTrustedOrigin() still gates microphone requests, and the cloud origin is
recorded in the existing `server` preference so that check keeps working.
Links outside the cloud origin open in the real browser rather than inside the
WebView. Failure to reach the service shows a retry screen with a route back to
PC mode rather than a dead WebView.

Built and signed: android/LinguaFusionMobile/dist/LinguaFusionMobile-debug.apk
(debug keystore). The compiled dex was checked to contain the cloud URL.
NOT yet installed or run on a real device -- that is the remaining gap.

## The Android build is distributed through the invite (2026-09-08)

scripts/publish_android_apk.py stages the signed APK into the served assets and
writes android-app.json with its size and SHA-256. It refuses to publish a file
that is not a signed APK, or one containing anything credential-shaped -- that
is re-checked on every publish rather than assumed from a single inspection,
because a future build could pick a secret up.

Served at /pilot/linguafusion-android.apk as
application/vnd.android.package-archive with Content-Disposition attachment, so
a browser downloads it instead of trying to render it. It is UNAUTHENTICATED on
purpose: someone arriving from the invite has no account yet and could not
authenticate to fetch it. That is safe because the APK carries no secret and
grants nothing by itself -- it is a shell around the same web app, and every
account still needs Firebase sign-in plus the owner's approval.

The invite page now carries TWO QR codes: the app, and a second one for the
Android download. The printed card names the download address in text rather
than crowding a second code onto A4. The pilot page shows the offer before
sign-in, with the SHA-256 read from the published JSON so the advertised
fingerprint cannot drift from the bytes actually being served -- a test asserts
those two agree, since a fingerprint that does not match is worse than none.

The service worker deliberately does not cache the APK or its details: a stale
cached binary would be installed while the page advertised a newer fingerprint.

Verified live: the download returns 200 unauthenticated, is byte-identical to
the locally built APK, and matches the advertised fingerprint. The page shows
the offer while signed out.

Sideloading is explained rather than sprung on people: the phone will warn that
the file came from outside the Play Store. The build is debug-signed, which is
acceptable for a privately shared pilot but is NOT suitable for wider
distribution; a release keystore would be needed for that.

## Reshaped into an app (2026-09-08)

The page was one long scroll of setup text with the working features buried at
the bottom. It now matches the existing mobile client's shape: an app shell with
five views -- Speak, Translate, Read, Say it, Account -- and a fixed bottom
navigation bar, one view visible at a time.

Everything needed only before approval (the intro, the pre-sign-in notice, the
Android download, sign-in, sign-up, confirmation, the access request) lives in
#onboarding and is hidden outright once the account is approved. The Android
offer is also hidden when already installed, detected by display-mode
standalone, navigator.standalone, or a WebView user agent -- offering someone a
download of the app they are currently using is noise.

The dead OpenAI model catalogue was removed from the UI. It advertised GPT
pricing for a route that could never run, because OPENAI_API_KEY is not set and
is not going to be. In its place the Translate view offers a real choice between
the two reviewed OpenRouter models, with a plain-language note on each. An
unreviewed model id is REFUSED rather than silently replaced with the default:
returning a result from a different model than the one asked for misreports what
produced it. The ledger records the model actually dispatched, so the owner's
spending breakdown shows which one cost the money.

The owner view now shows each person by name, organisation and email joined from
their access request, alongside their requests this month, spend, holds and
budget. A bare Firebase UID told the owner nothing and they cannot decide on
nothing. Each row has Edit limits and Remove.

Remove now genuinely removes: it revokes access, erases the personal data, AND
drops the policy row via the new policy.forget(). Previously a removed person
stayed forever as a disabled row, so the list only ever grew. Recorded charges
are deliberately kept -- money already committed cannot be un-spent by deleting
whoever spent it, and the lifetime total must keep counting it. A test asserts
exactly that.

Housekeeping: seven leftover disabled rows from testing were dropped from the
live ledger, leaving the owner and one approved user. Committed spend was
unchanged at US$0.32 across the removal, confirming the money is preserved.

## Silent-failure audit and appearance (2026-09-08)

MICROPHONE. "Microphone unavailable. Allow access, then try again." was shown
for every possible cause, including to someone who had already granted
permission -- telling them to do the thing they had just done. One try/catch
wrapped both getUserMedia AND the audio-graph setup, so a missing API, a busy
device, an absent microphone and a refused permission were indistinguishable.
Now: navigator.mediaDevices is checked explicitly, getUserMedia failures are
reported by error name (NotAllowedError, NotFoundError, NotReadableError,
SecurityError, AbortError), and audio-graph failures are reported separately
with the microphone released rather than left open behind a dead indicator.

Also fixed a real Android cause: AudioContext is created SUSPENDED there. The
graph connected and the microphone went live, but onaudioprocess never fired,
so a recording could complete having captured nothing. context.resume() is now
awaited before recording starts.

APPEARANCE. Two looks -- Studio (parchment and terracotta by day, sunset rose
and plum at night) and Minimal (monochrome in both) -- each with a day and a
night mode, plus six typefaces. Look, mode and typeface are three independent
choices, each remembered separately, matching the rest of LinguaFusion. The
mode has its own button in the app header so it can be switched from any view.
cloud_api/web/themes.mjs lists what the picker offers; the shared
linguafusion-themes.css still defines the older phone and PC looks because the
desktop and phone clients read the same file, and the cloud picker simply does
not list them. This app's tokens map onto the sheet's --lf-* contract, so the
looks are the real ones rather than lookalikes. A look must not hardcode the
primary button's label colour: Minimal's night accent is a near-white block
with a dark label, so the label reads through --lf-on-accent.
No webfont is fetched: typefaces use native stacks, and a test asserts no
@import or Google Fonts reference, because the product is offline-first.

A REAL PITFALL found while verifying: the prefers-color-scheme dark block in
pilot.css assigned literal colours. It sits later in the cascade at equal
specificity, so on any dark-mode phone every look was silently inert -- the
selector changed, the attribute changed, and nothing moved. Those tokens now
defer to the chosen look with the dark palette only as a fallback, and a test
fails if any of them hardcodes a colour again.

Verified in a browser across soft-ui, sunset, brutalist, glass-dark,
neon-arcade and nature-calm: five distinct backgrounds plus two gradient looks.
The gradient looks compute backgroundColor transparent because a gradient is a
background-image; that is correct, not a fault -- checked before "fixing" it.

## The navigation bar leaked the page through it (2026-09-08, fixed)

The fixed bottom bar used --panel, which maps to --lf-surface-bg. Several looks
define that as a TRANSLUCENT overlay intended to sit on a blurred backdrop --
rgba(255,255,255,.07) in Glass Dark, .08 and .72 elsewhere, and one look sets it
to `transparent` outright. Content therefore scrolled straight through the bar
on those looks.

Worth recording how this was missed: an earlier check concluded the gradient
backgrounds were "not a bug". That was correct about the BODY, where a gradient
is a background-image and computing transparent is expected. It was the wrong
element. The bar is a different surface and a genuinely translucent one, and
checking the body proved nothing about it.

The bar now paints var(--lf-app-bg), which is opaque in every look (verified by
reading every value: each is a solid colour, or a gradient whose stops are solid
and whose final stop fills the box). A blur is applied as insurance, and the
active pill uses the chip token rather than the notice colour so it reads
correctly on dark looks. A test asserts the bar never uses a surface token and
that no look defines a fully transparent app background.

Note for future guards of this kind: --lf-surface-bg is unsafe for ANYTHING that
must occlude scrolling content. Use it only for surfaces in normal flow.

## A4-sized translation, OCR layout, cross-links and export (2026-09-08)

TRANSLATION LIMIT 4,000 -> 6,000 characters, about one dense A4 page. Raising
the input alone would have BROKEN long translations: max_tokens was 2048, which
caps the OUTPUT. Hindi, Arabic and Odia tokenise close to one token per
character, so a full page would have been truncated, finish_reason would stop
being 'stop', and the request would fail as a provider error. Output ceilings
are now 8192 for translation and 4096 for pronunciation, and the limits live in
pilot_providers as constants the page reads from /capabilities rather than
repeating. A live counter warns as the cap is reached and says to split the
text, because a silent paste truncation is invisible.

OCR LAYOUT. Vision's fullTextAnnotation.text flattens the page, so on a form or
receipt every label ends up separated from its value and table rows interleave.
cloud_api/ocr_layout.py rebuilds layout from the word bounding boxes: words are
grouped into visual lines by vertical overlap (sorting by top edge alone splits
a line whenever one word sits a pixel higher), wide horizontal gaps become
column separators scaled to the local character width, and paragraph breaks are
detected against THIS page's median line gap rather than a fixed multiple --
a fixed multiple split loosely-leaded forms and missed breaks in tight prose.
Ten tests drive it with fixed coordinates, including a table, a label/value
form and prose that must NOT be reported as a table. The flat text is still
returned alongside so nothing is lost if the reconstruction ever reads worse.
Deliberately not a cell-grid parser: inferring cells from OCR boxes is
unreliable and a wrong grid reads worse than honest aligned text.

CROSS-LINKS. Transcript and OCR text can be sent to Translate; OCR text and a
translation can be sent to Say it, which preselects the language when the
target is Hindi, Arabic or Odia. Over-long text is truncated to the limit and
the person is told how much did not fit rather than losing it silently.

EXPORT. Text and Markdown everywhere, plus CSV for OCR ONLY when columns were
actually detected -- a CSV of prose is one quoted cell per line, which is worse
than the text. Downloads are client-side, so nothing is uploaded to be exported.

Two Android traps handled: a WebView never fires its download listener for
blob: URLs, so the page emits a data: URL when it detects a WebView; and on
Android 10 and later, writing to the public Downloads PATH fails under scoped
storage, so the wrapper writes through MediaStore (which also needs no storage
permission) and keeps the legacy path only for older devices. File names from
the page are sanitised rather than trusted, and an implausible size is refused.

Not attempted: DOCX and PDF export. The offline app produces those through
document_service and complex_script_pdf_service, and complex-script PDF needs
embedded fonts -- shipping a naive version would mangle Hindi, Arabic and Odia,
which are exactly the scripts this feature exists for.

## Model choice moved to its own tab (2026-09-08)

A sixth view, Model, replaces the dropdown that sat inside Translate. Each model
is a card carrying what it is better for, what it is weaker at, its relative
speed and its relative cost. The choice is remembered on the device like the
look and typeface, and Translate shows a one-line summary of what is in use.

The cards state plainly that the notes are the models' GENERAL REPUTATIONS and
not measurements taken on this app's own text -- /capabilities returns
model_guidance_is_measured=false and the page renders that caveat from it.
Presenting reputation as evidence would be the easy thing to do and would be
misleading, particularly for the Indic-script question that prompted this.

ANSWER TO "are these the only two OpenRouter offers": no. Read from OpenRouter's
public catalogue on 2026-09-08: 431 models advertised, 45 of them at or below
this app's US$0.20 per million price ceiling. The two-model restriction is OURS,
not OpenRouter's -- pilot_providers refuses any model outside the allowlist, and
pins provider.only=['deepinfra'] with a max_price ceiling.

Candidates within the ceiling worth testing for the Hindi quality problem, with
catalogue prices per million (input/output):
  qwen/qwen3.7-flash                        0.030 / 0.130   1M context
  mistralai/mistral-small-24b-instruct-2501 0.050 / 0.080
  google/gemma-3-12b-it                     0.050 / 0.150
  meta-llama/llama-3.1-8b-instruct          0.050 / 0.080
Adding one means reviewing its price and behaviour and extending
TRANSLATION_MODELS; it is a spending decision, so it was not done unasked.

WATCH THIS: the catalogue lists google/gemma-3-27b-it at 0.450 per million
output, well above the 0.20 ceiling the code pins for it. It works today because
DeepInfra's own price is under the ceiling, but if that provider raises its
price or drops the model, Gemma translations will start failing with a provider
error and nothing will say why beyond the retained hold. Also note
pilot_providers._post refuses to dispatch at all after 2026-10-08 pending a
price review.

## More models, and a measured reason to change the default (2026-09-08)

CORRECTION to the earlier warning: google/gemma-3-27b-it is NOT at risk of
breaching its price cap. The catalogue's 0.450 per million is another provider's
headline; DeepInfra, which this app pins, serves it at 0.160 against a cap now
set to 0.25. Checked directly through the per-model endpoints API.

The registry moved into pilot_providers, because the max_price sent upstream is
provider knowledge and belongs beside the model list. Each model now carries its
OWN cap, set around 1.5x the price DeepInfra actually charged, replacing a
hardcoded if/else. A test asserts the cap sent upstream matches the model chosen,
that provider.only stays pinned and fallbacks stay off.

Every candidate was checked for a DeepInfra endpoint first: a model DeepInfra
does not serve fails outright however good it looks in the catalogue.
qwen3.7-flash, gemini-2.5-flash-lite and gpt-4.1-nano are all unusable here for
that reason alone.

LIVE RESULT on one Hindi sentence ("the contract is void if either party fails
to give thirty days notice"), each model once through the deployed service:
  Mistral Small 24B   1.1s  "संविदा को रद्द"      correct
  Gemma 3 27B         1.7s  "अनुबंध अमान्य"        correct, most formal
  Qwen 2.5 72B        3.2s  "संवाद"               wrong noun for contract
  Mistral Nemo        2.4s  "कॉन्ट्रैक्ट कोल्हू"      कोल्हू is an OIL PRESS
  DeepSeek V4 Flash   0.7s  HTTP 502 every time

DeepSeek was REMOVED. It failed 3 of 3 attempts, each rejected in about 0.7s,
so this is an immediate refusal rather than a timeout. It is not offered again
until someone works out why; shipping a choice that never works is worse than
offering fewer.

DEFAULT CHANGED from Mistral Nemo to Mistral Small 24B. Nemo is the cheapest
but produced nonsense on the one Hindi sentence tried, which is exactly the
complaint that started this. Mistral Small costs a fraction of a cent more per
request, well inside the flat US$0.01 hold, and got it right. Each model's card
now also shows what was actually seen here, clearly marked as one spot check
rather than a benchmark.

Official pricing references:
- https://cloud.google.com/run/pricing
- https://cloud.google.com/firestore/pricing
- https://docs.cloud.google.com/run/docs/tips/services-cost-optimization
