"""End-to-end pairing test."""
import requests, json, os, sys

BASE = "http://localhost:8000"

# Step 1: Check health
r = requests.get(f"{BASE}/health", timeout=5)
print("1. Health:", r.status_code, "ok" if r.json().get("ok") else "FAIL")

# Step 2: Get the admin key
sys.path.insert(0, ".")
from backend.config.paths import STORAGE_DIR
admin_key_file = STORAGE_DIR / "admin_key.txt"
if admin_key_file.exists():
    admin_key = admin_key_file.read_text().strip()
    print(f"2. Admin key found: {admin_key[:8]}...")
else:
    admin_key = os.environ.get("LINGUAFUSION_ADMIN_KEY", "")
    print(f"2. Admin key from env: {admin_key[:8] if admin_key else 'NONE'}")

# Step 3: Create a pairing via owner-api
r = requests.post(
    f"{BASE}/owner-api/pairings",
    json={"label": "Test Phone", "expires_minutes": 15, "public_url": "https://linguafusion.fyi"},
    headers={"X-Admin-Key": admin_key},
)
print(f"3. Create pairing: {r.status_code}")
if r.status_code != 200:
    print("   RESPONSE:", r.text[:300])
    sys.exit(1)

pairing = r.json()["pairing"]
token = pairing["token"]
print(f"   Token: {token[:12]}...")

# Step 4: Exchange pairing token (simulating phone sending form data like app.js does)
r = requests.post(
    f"{BASE}/api/mobile/pair/exchange",
    data={"token": token, "device_name": "Test iPhone", "platform": "ios"},
)
print(f"4. Exchange: {r.status_code}")
data = r.json()
print(f"   Response keys: {list(data.keys())}")
has_api_key = "api_key" in data
has_device_key = "device_key" in data
print(f"   Has api_key: {has_api_key}, Has device_key: {has_device_key}")
device_key = data.get("api_key") or data.get("device_key") or ""
if not device_key:
    print("   ERROR: No key received!")
    sys.exit(1)
print(f"   Key: {device_key[:12]}...")

# Step 5: Verify the key at the correct URL
r = requests.get(f"{BASE}/pair/verify", headers={"X-API-Key": device_key})
print(f"5. Verify /pair/verify: {r.status_code} {r.json()}")

# Step 6: Try the old wrong URL
r = requests.get(f"{BASE}/api/pair/verify", headers={"X-API-Key": device_key})
print(f"6. Verify /api/pair/verify (old URL): {r.status_code}")

# Step 7: Test an authenticated API call (translate)
r = requests.post(
    f"{BASE}/translate",
    data={"text": "Hello world", "source_lang": "en", "target_lang": "de"},
    headers={"X-API-Key": device_key},
)
print(f"7. Translate: {r.status_code} ok={r.json().get('ok')}")

print("\n=== ALL TESTS PASSED ===" if r.status_code == 200 else "\n=== SOME TESTS FAILED ===")
