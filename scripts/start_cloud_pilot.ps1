$ErrorActionPreference = 'Stop'
$pilotRoot = Split-Path -Parent $PSScriptRoot
$pilotPython = Join-Path $pilotRoot '.venv-cloud\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pilotPython)) { throw 'The isolated cloud Python environment is missing.' }
$env:LF_FIREBASE_PROJECT_ID = 'linguafusion-f24fe'
$env:LF_CLOUD_ALLOWED_UIDS = 'kLqjJka0cHXTCZX0TQxA2QMlzKi1'
# This launcher is for sign-in testing only; never inherit a paid-AI opt-in.
$env:LF_CLOUD_AI_ENABLED = '0'
$env:LF_CLOUD_OWNER_UID = 'kLqjJka0cHXTCZX0TQxA2QMlzKi1'
$env:LF_CLOUD_LOCAL_POLICY_DB = Join-Path $pilotRoot 'cloud_api\local-data\policy.sqlite3'
Push-Location $pilotRoot
try {
    Write-Host 'Local cloud pilot: http://127.0.0.1:8081/pilot/'
    Write-Host 'Cloud AI is OFF. Backend approval checks require Google Application Default Credentials.'
    & $pilotPython -m uvicorn cloud_api.app:app --host 127.0.0.1 --port 8081 --no-access-log --no-proxy-headers
    if ($LASTEXITCODE -ne 0) { throw "Pilot exited with code $LASTEXITCODE" }
} finally { Pop-Location }
