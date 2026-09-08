param([switch]$AllLanguages, [switch]$ReadingGuide)
$ErrorActionPreference = 'Stop'
$testRoot = Split-Path -Parent $PSScriptRoot
$keyPath = Join-Path $testRoot 'cloud_api\local-data\credentials\openrouter.xml'
$oldTestKey = $env:LF_TEST_OPENROUTER_KEY
$secureTestKey = $null
$keyPointer = [IntPtr]::Zero
try {
    $secureTestKey = Import-Clixml -LiteralPath $keyPath
    if ($secureTestKey -isnot [Security.SecureString]) { throw 'Invalid encrypted credential file.' }
    $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureTestKey)
    $env:LF_TEST_OPENROUTER_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    $testArgs = @()
    if ($AllLanguages) { $testArgs += '--all-languages' }
    if ($ReadingGuide) { $testArgs += '--reading-guide' }
    & (Join-Path $testRoot '.venv-cloud\Scripts\python.exe') (Join-Path $PSScriptRoot 'test_cloud_translation.py') @testArgs
    $testExit = $LASTEXITCODE
} finally {
    $env:LF_TEST_OPENROUTER_KEY = $oldTestKey
    if ($keyPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer) }
    if ($secureTestKey) { $secureTestKey.Dispose() }
}
exit $testExit
