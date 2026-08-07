param(
    [Parameter(Mandatory = $true)]
    [string]$PublicUrl,
    [int]$Port = 8000,
    [switch]$NoOpenDashboard
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$PublicUrl = $PublicUrl.Trim().TrimEnd("/")
if (-not $PublicUrl.StartsWith("https://")) {
    throw "Friend access requires a stable HTTPS address, for example https://linguafusion.example.com"
}

function Get-OrCreateSecret([string]$Path, [int]$ByteCount) {
    New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null
    if (Test-Path -LiteralPath $Path) {
        $existing = (Get-Content -LiteralPath $Path -Raw).Trim()
        if ($existing) { return $existing }
    }
    $bytes = New-Object byte[] $ByteCount
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    $secret = -join ($bytes | ForEach-Object { $_.ToString("x2") })
    [System.IO.File]::WriteAllText($Path, $secret, (New-Object System.Text.UTF8Encoding($false)))
    return $secret
}

$apiKey = Get-OrCreateSecret (Join-Path $PWD "backend\storage\mobile_api_key.txt") 32
$adminKey = Get-OrCreateSecret (Join-Path $PWD "backend\storage\mobile_admin_key.txt") 36

$env:LINGUAFUSION_API_KEY = $apiKey
$env:LINGUAFUSION_ADMIN_KEY = $adminKey
$env:LINGUAFUSION_PUBLIC_URL = $PublicUrl
$env:LF_TRUST_PROXY_HEADERS = "1"
$env:LF_PUBLIC_ACCESS = "1"
$env:LF_WHISPER_MODEL = "medium"
$env:LF_WHISPER_DEVICE = "cuda"
$env:LF_ODIA_ASR_DEVICE = "cuda"
$env:LF_MMS_TTS_DEVICE = "cuda"
$env:NLLB_DEVICE = "cuda"
$env:NLLB_COMPUTE_TYPE = "int8"

$ownerUrl = "http://127.0.0.1:${Port}/owner/"
Write-Host ""
Write-Host "LinguaFusion friend backend" -ForegroundColor Cyan
Write-Host "Public app address: $PublicUrl" -ForegroundColor Green
Write-Host "Owner dashboard: $ownerUrl" -ForegroundColor Green
Write-Host "Owner admin key: $adminKey" -ForegroundColor Yellow
Write-Host ""
Write-Host "The admin key controls every friend device. Never put it in a QR code or send it to a friend." -ForegroundColor Yellow
Write-Host "Keep the configured HTTPS tunnel running. Do not forward port $Port on your router." -ForegroundColor Gray
Write-Host "Confirm the -500 MHz GPU memory underclock is active before inference." -ForegroundColor Gray
Write-Host ""

if (-not $NoOpenDashboard) {
    Start-Process $ownerUrl
}

& .\.venv\Scripts\python.exe -m uvicorn backend.server:app --host 127.0.0.1 --port $Port
