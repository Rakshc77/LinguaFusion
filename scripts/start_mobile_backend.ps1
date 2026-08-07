param(
    [switch]$Reload,
    [switch]$NoQr,
    [switch]$ShowKey,
    [switch]$PairNewPhone
)

Set-Location $PSScriptRoot\..

$keyFile = Join-Path $PWD "backend\storage\mobile_api_key.txt"
New-Item -ItemType Directory -Force -Path (Split-Path $keyFile) | Out-Null
if (-not (Test-Path -LiteralPath $keyFile)) {
    $bytes = New-Object byte[] 24
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    $key = -join ($bytes | ForEach-Object { $_.ToString("x2") })
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($keyFile, $key, $utf8NoBom)
}
$key = (Get-Content -LiteralPath $keyFile -Raw).Trim()
$env:LINGUAFUSION_API_KEY = $key

$pairedFile = Join-Path $PWD "backend\storage\mobile_paired.flag"
$needsPairing = $PairNewPhone -or -not (Test-Path -LiteralPath $pairedFile)
$pairingToken = ""
if ($needsPairing) {
    # A fresh one-use token lets the phone obtain the persistent key by
    # scanning a QR code. The long-lived key never appears in the QR URL.
    $pairBytes = New-Object byte[] 16
    $pairRng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $pairRng.GetBytes($pairBytes)
    $pairRng.Dispose()
    $pairingToken = -join ($pairBytes | ForEach-Object { $_.ToString("x2") })
    $env:LINGUAFUSION_PAIRING_TOKEN = $pairingToken
} else {
    Remove-Item Env:LINGUAFUSION_PAIRING_TOKEN -ErrorAction SilentlyContinue
}

$env:LF_WHISPER_MODEL = "medium"
$env:LF_WHISPER_DEVICE = "cuda"
$env:NLLB_DEVICE = "cuda"
$env:NLLB_COMPUTE_TYPE = "int8"

$networkAddresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.PrefixOrigin -ne "WellKnown" -and
        $_.AddressState -eq "Preferred"
    })

# Bind to the active physical LAN address instead of 0.0.0.0. Some Windows
# configurations reserve or already occupy a wildcard bind even though the
# specific Wi-Fi/Ethernet address is available (WinError 10013/10048).
$mobileHost = ($networkAddresses |
    Where-Object { $_.InterfaceAlias -match "Wi-Fi|Ethernet" } |
    Select-Object -First 1 -ExpandProperty IPAddress)
if (-not $mobileHost) {
    $mobileHost = ($networkAddresses | Select-Object -First 1 -ExpandProperty IPAddress)
}
if (-not $mobileHost) {
    Write-Error "No active private IPv4 network address was found. Connect the PC to Wi-Fi or Ethernet and try again."
    exit 1
}

Write-Host ""
Write-Host "LinguaFusion mobile pairing" -ForegroundColor Cyan
Write-Host "Mobile URL: http://${mobileHost}:8000/mobile/" -ForegroundColor Green
if ($needsPairing) {
    Write-Host "Scan the QR window once; this phone will reconnect automatically afterward." -ForegroundColor Yellow
} else {
    Write-Host "Previously paired phones will reconnect automatically." -ForegroundColor Green
    Write-Host "To add another phone, start with: .\scripts\start_mobile_backend.ps1 -PairNewPhone" -ForegroundColor DarkGray
}
if ($ShowKey) {
    Write-Host "Manual API key: $key" -ForegroundColor Yellow
}
Write-Host "Keep this window open and allow Private network access if Windows asks." -ForegroundColor Gray
Write-Host "Confirm the -500 MHz GPU memory underclock is active before inference." -ForegroundColor Gray
Write-Host ""

$serverBase = "http://${mobileHost}:8000"
$webPairingUrl = if ($needsPairing) { "${serverBase}/mobile/?pair=${pairingToken}" } else { "" }
$appPairingUrl = if ($needsPairing) {
    $encodedServer = [Uri]::EscapeDataString($serverBase)
    $encodedToken = [Uri]::EscapeDataString($pairingToken)
    "linguafusion://pair?server=${encodedServer}&token=${encodedToken}"
} else { "" }
if ($needsPairing -and -not $NoQr) {
    $pairingCard = Join-Path $PWD "temp\mobile_pairing.html"
    & .\.venv\Scripts\python.exe .\scripts\generate_mobile_pairing_qr.py --url $appPairingUrl --fallback-url $webPairingUrl --output $pairingCard
    if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $pairingCard)) {
        Start-Process -FilePath $pairingCard
    } else {
        Write-Warning "Could not create the QR card. Use the pairing link shown below."
    }
}
if ($needsPairing) {
    Write-Host "One-time app pairing link: $appPairingUrl" -ForegroundColor DarkGray
    Write-Host "Browser fallback: $webPairingUrl" -ForegroundColor DarkGray
    Write-Host "Pairing link expires after 15 minutes and works once." -ForegroundColor DarkGray
}
Write-Host ""

$uvicornArgs = @("-m", "uvicorn", "backend.server:app", "--host", $mobileHost, "--port", "8000")
if ($Reload) {
    $uvicornArgs += "--reload"
}
& .\.venv\Scripts\python.exe @uvicornArgs
