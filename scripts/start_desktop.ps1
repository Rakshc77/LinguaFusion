Set-Location $PSScriptRoot\..

# Start from the project root as a package module. Running desktop\main.py as
# a standalone file puts only the desktop folder on sys.path, which prevents
# imports such as `from desktop.iconography import ...` from resolving.
& .\.venv\Scripts\python.exe -m desktop.main
