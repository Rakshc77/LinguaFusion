$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    throw "The project virtual environment was not found. Run the normal dependency setup first."
}

Write-Host "Installing local speech, voice and OCR packs for all seven LinguaFusion languages." -ForegroundColor Cyan
& .\.venv\Scripts\python.exe .\scripts\install_language_models.py
