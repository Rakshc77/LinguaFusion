$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    throw "The project virtual environment was not found. Run the normal dependency setup first."
}

Write-Host "This one-time setup downloads official offline OCR/TTS models and the larger Odia speech model." -ForegroundColor Cyan
& .\.venv\Scripts\python.exe .\scripts\install_arabic_odia_models.py
