$ErrorActionPreference = 'Stop'
$sdkCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'),
    'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd',
    'C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
)
$sdkCommand = Get-Command gcloud.cmd -ErrorAction SilentlyContinue
$sdkPath = if ($sdkCommand) { $sdkCommand.Source } else {
    $sdkCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $sdkPath) { throw 'Google Cloud CLI is not installed. Complete installation first.' }
Write-Host 'Sign in privately with the Google account that owns Firebase project linguafusion-f24fe.'
Write-Host 'Review the Google consent screen. Local developer credentials inherit your account permissions.'
Write-Host 'Do not paste passwords, authorization codes or credential files into chat.'
Write-Host 'This does not deploy services, enable billing or turn on cloud AI.'
& $sdkPath auth application-default login --project=linguafusion-f24fe
if ($LASTEXITCODE -ne 0) { throw 'Google authorization did not complete. See the message above.' }
Write-Host 'Authorization completed. Return to the pilot and select Check cloud access.'
Write-Host 'To revoke these local developer credentials later: gcloud auth application-default revoke'
