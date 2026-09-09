# Run interactively as the Windows account that will run the local pilot.
# Export-Clixml protects SecureString values with Windows DPAPI, bound to this
# Windows user and computer. These files are NOT cloud-deployment credentials.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'This private key setup requires Windows.'
}
$keyRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'cloud_api\local-data\credentials'
New-Item -ItemType Directory -Path $keyRoot -Force | Out-Null
Write-Host 'LinguaFusion private key setup'
Write-Host 'Keys are hidden while typing and encrypted for this Windows account.'
Write-Host 'No API requests, billing changes, or cloud deployment will be performed.'
Write-Host 'Do not share these files, even though they are encrypted.'
foreach ($providerName in @('openrouter', 'groq')) {
    $keyFile = Join-Path $keyRoot ($providerName + '.xml')
    if (Test-Path -LiteralPath $keyFile) {
        Write-Host "$providerName already has a saved credential; leaving it unchanged."
        continue
    }
    $providerSecret = Read-Host "Paste the $providerName API key (hidden; Enter to skip)" -AsSecureString
    try {
        if ($providerSecret.Length -eq 0) {
            Write-Host "$providerName skipped."
            continue
        }
        $providerSecret | Export-Clixml -LiteralPath $keyFile
        Write-Host "$providerName saved securely."
    } finally {
        $providerSecret.Dispose()
        Remove-Variable providerSecret -ErrorAction SilentlyContinue
    }
}
Write-Host 'Setup finished. Paid testing remains disabled until the combined test budget is wired in.'
