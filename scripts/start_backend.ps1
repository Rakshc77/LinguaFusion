param(
    [switch]$NoReload
)

Set-Location $PSScriptRoot\..

# faster-whisper model size: tiny, base, small, medium, large-v3, distil-large-v3
$env:LF_WHISPER_MODEL = "medium"

# Require CUDA for transcription. This deliberately prevents a silent CPU
# fallback; startup/transcription will report a clear model-load error if CUDA
# is unavailable. Keep the -500 MHz MSI Afterburner memory underclock active.
$env:LF_WHISPER_DEVICE = "cuda"

# Emergency safe fallback if GPU instability ever recurs:
# $env:LF_WHISPER_DEVICE = "cpu"

# Keep NLLB translation on the GPU too. It remains independent of Ollama and
# uses its purpose-built translation model rather than a chat-model rewrite.
$env:NLLB_DEVICE = "cuda"
$env:NLLB_COMPUTE_TYPE = "int8"

# The permanent Cloudflare tunnel is an automatic Windows service. Advertise
# its stable address without creating a temporary trycloudflare tunnel.
$env:LINGUAFUSION_PUBLIC_URL = "https://linguafusion.fyi"
$env:LF_TRUST_PROXY_HEADERS = "1"
$env:LF_PUBLIC_ACCESS = "1"
Remove-Item Env:LF_AUTO_TUNNEL -ErrorAction SilentlyContinue

$uvicornArgs = @("-m", "uvicorn", "backend.server:app", "--host", "127.0.0.1", "--port", "8000", "--no-proxy-headers")
if (-not $NoReload) {
    $uvicornArgs += "--reload"
}

& .\.venv\Scripts\python.exe @uvicornArgs
