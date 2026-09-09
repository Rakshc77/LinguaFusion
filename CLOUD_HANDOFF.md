# PC-independent LinguaFusion continuation

Updated 2026-09-09. Start with CODEX_CURRENT_STATE.md; this file retains cloud operations details.

## Application and source

Existing repository: https://github.com/Rakshc77/LinguaFusion (public).
Continuation branch: `codex/studio-minimal-appearance`.
Cloud baseline branch: `codex/cloud-handoff-microphone`.
Production: https://linguafusion-cloud-pilot-jl77ipbeua-ey.a.run.app/pilot/
Cloud Run service `linguafusion-cloud-pilot`, project `linguafusion-f24fe`,
region `europe-west3`. Firebase sign-in and owner approval; Firestore-backed
policy and spending ledger; OpenRouter translation/pronunciation, Groq speech,
Google Vision OCR. Production needs no PC, local Ollama, tunnel or local disk.
The offline desktop/PC-paired clients remain separate.

## September 9 appearance update (source only)

Cloud/PWA/Android cloud UI now offers only Studio and Minimal, with independent
Day/Night and typeface controls. Studio day uses Warm Editorial parchment
(#f4efe4), ink (#2b2622) and terracotta (#b04a2f). Studio night uses Sunset
rose (#f24e7a) on plum (#1a1015). Minimal stays neutral in both modes.
Removed look choices migrate to Studio or Minimal and preserve legacy dark
selection and font. Static cache version is v3-appearance. Offline inference
is still planned, not implemented. These source changes are not yet deployed.
The user reports the Android 1.5 microphone update works smoothly on the S26 Ultra.

## September 8 microphone update

Samsung S26 Ultra: owner confirmed cloud speech works well in Chrome, but APK
WebView returns NotReadableError. Root cause inside the device WebView is not
proven. Android 1.5 (version code 6) bypasses that path using a native AudioRecord
dialog. Only a same-origin, top-level user gesture can request it; recording
requires a second explicit native Start tap. No cloud JavaScript interface is
installed. Cancel/background releases audio; Stop sends mono 16-kHz PCM WAV;
cloud capture is bounded to 60 seconds. Local PC recording keeps its prior limit.

Browser recording fixes serialize Start, release late streams after cancellation,
close failed contexts, bound PCM frames before WAV encoding, serialize uploads,
and discard stale native callbacks after logout/navigation. The owner confirmed the updated APK records and transcribes smoothly on the
S26 Ultra in this conversation. This does not verify every language or device.
APK is debug-signed; production release signing is NOT configured.

## Verified tests

- 141 cloud Python tests passed; 8 invite-image tests skipped (optional image dependencies).
- Current source: 45 Node tests pass, including recording lifecycle and appearance migration tests.
- Android compilation and v2/v3 signature verification passed; expected native
  recording methods found inside the built APK.
- Cloud Build `cd8832a2-a7dc-4630-bbf0-012ba0cde2fd` succeeded.
- New image: `sha256:a96f57c07148ec8e6ec17d6888ee8bb6d4f811b7fefabba0c902edaf7977f9b4`.
- Previous image for rollback: `sha256:032a00d66f666b2c71843ca364b6af5c04d46f79ae8c737ce2b43216f2743154`.

## Run tests in a cloud development environment

Use Python 3.11 and Node 22, without GPU or provider credentials:

```sh
python -m pip install -r cloud_api/requirements.txt 'pytest>=8,<10'
python -m pytest cloud_api -o python_files=test_*.py -q
node --test cloud_api/web/*.test.mjs
```

Root pytest.ini otherwise only discovers legacy backend tests. The GitHub
workflow runs the cloud suites without secrets and does NOT deploy automatically.
Do not install the desktop GPU requirements just to work on the cloud service.

## Continue from phone

In Codex Cloud connect this existing GitHub repository, create/select its cloud
environment, and explicitly select `codex/studio-minimal-appearance`. Start by
asking it to read this handover and run the above tests. The current coding workspace can edit and test without the owner’s PC; its
local commits still need publishing to GitHub before another environment can fetch them.

GitHub login, push success, and Codex environment creation must each be verified;
having the source locally or a Cloud Run deployment does not prove them.
Cloud editing/testing is independent of production deployment access. Do not
copy Windows ADC, DPAPI-encrypted keys or service-account JSON into GitHub/Codex.
For deployments use approved Google Cloud identity (for example Cloud Shell)
or set up narrowly scoped workload identity in a separate reviewed step.

## Deploy tooling and limits

`scripts/deploy_cloud_update.py` defaults to read-only. `--build` sends only
the Docker allowlist to the existing Cloud Build bucket. `--status BUILD_ID`
checks the build; `--promote BUILD_ID` changes only the service image, with an
etag to reject concurrent changes. It does not change IAM, secrets or budgets.
Build/hosting charges are separate from AI token spending.

The small public APK download is included so clean cloud builds and its
fingerprint tests are reproducible. To change it, rebuild with the
Android SDK and the owner's existing signing key, then run
`scripts/publish_android_apk.py` to verify and stage it. A clean clone lacks that
key and cannot produce an in-place update signed as the existing APK. Do not
silently replace the published APK with a different signature. The strict cloud
build allowlist requires a staged APK; retain/download the verified published
artifact for cloud-only changes, or arrange secure signing separately.

Live ledger checked before this update: USD 27 lifetime ceiling, USD 0.46
committed/held (not a provider invoice), USD 26.54 remaining. Preserve it; do not
reset or reopen the closed local combined-test ledger. Google billing alerts
are NOT a hard infrastructure spending cap. Pricing review expires 2026-10-08.

Remaining: broader device/off-LAN acceptance, production
signing, automatic deployment identity, provider-failure investigation,
dependency/security review. Do not claim these are completed.

Private historical handovers, local credentials/settings, usage ledgers and
recordings are excluded from this public source handoff.
