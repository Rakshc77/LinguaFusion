Set-Location $PSScriptRoot\..
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.server:app --reload --host 0.0.0.0 --port 8000
