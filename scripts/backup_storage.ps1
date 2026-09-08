param([string]$Destination = '')
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$backupArgs = @((Join-Path $PSScriptRoot 'storage_backup.py'), 'create')
if ($Destination) { $backupArgs += @('--destination', $Destination) }
& (Join-Path $project '.venv\Scripts\python.exe') @backupArgs
if ($LASTEXITCODE -ne 0) { throw 'Backup failed. Existing backups were not replaced.' }
Write-Host 'Backup verified. It contains private data and device keys; keep it private.'
