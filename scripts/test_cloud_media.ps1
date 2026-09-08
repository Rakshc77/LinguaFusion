$ErrorActionPreference = 'Stop'
$mediaRoot = Split-Path -Parent $PSScriptRoot
$sampleRoot = Join-Path $mediaRoot 'cloud_api\local-data\synthetic-tests'
New-Item -ItemType Directory -Path $sampleRoot -Force | Out-Null
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
    $speaker.SetOutputToWaveFile((Join-Path $sampleRoot 'speech.wav'), $format)
    $speaker.Speak('Hello. The train leaves at two thirty. Please bring your ticket.')
} finally { $speaker.Dispose() }
Add-Type -AssemblyName System.Drawing
$bitmap = New-Object System.Drawing.Bitmap(1000, 200)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$font = New-Object System.Drawing.Font('Arial', 32)
try {
    $graphics.Clear([System.Drawing.Color]::White)
    $graphics.DrawString('LinguaFusion test: Train 14:30', $font, [System.Drawing.Brushes]::Black, 20, 50)
    $bitmap.Save((Join-Path $sampleRoot 'ocr.png'), [System.Drawing.Imaging.ImageFormat]::Png)
} finally { $font.Dispose(); $graphics.Dispose(); $bitmap.Dispose() }
$oldKey = $env:LF_TEST_GROQ_KEY
$secret = $null
$pointer = [IntPtr]::Zero
try {
    $secret = Import-Clixml -LiteralPath (Join-Path $mediaRoot 'cloud_api\local-data\credentials\groq.xml')
    if ($secret -isnot [Security.SecureString]) { throw 'Invalid credential file' }
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    $env:LF_TEST_GROQ_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    & (Join-Path $mediaRoot '.venv-cloud\Scripts\python.exe') (Join-Path $PSScriptRoot 'test_cloud_media.py')
    $mediaExit = $LASTEXITCODE
} finally {
    $env:LF_TEST_GROQ_KEY = $oldKey
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    if ($secret) { $secret.Dispose() }
}
exit $mediaExit
