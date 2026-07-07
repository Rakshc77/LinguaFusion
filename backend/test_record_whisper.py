import sounddevice as sd
from scipy.io.wavfile import write
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WHISPER_EXE = ROOT / "tools" / "whispercpp" / "Release" / "whisper-cli.exe"
MODEL_PATH = ROOT / "models" / "whisper" / "ggml-small.bin"
TEMP_DIR = ROOT / "temp"
AUDIO_PATH = TEMP_DIR / "test.wav"

TEMP_DIR.mkdir(exist_ok=True)

print("Recording for 5 seconds...")
sample_rate = 16000
audio = sd.rec(
    int(5 * sample_rate),
    samplerate=sample_rate,
    channels=1,
    dtype="int16"
)
sd.wait()

write(AUDIO_PATH, sample_rate, audio)
print(f"Saved audio to: {AUDIO_PATH}")

print("Running Whisper...")

command = [
    str(WHISPER_EXE),
    "-m", str(MODEL_PATH),
    "-f", str(AUDIO_PATH),
    "-l", "auto",
    "--print-progress",
    "false"
]

result = subprocess.run(
    command,
    capture_output=True,
    text=True
)

print("TRANSCRIPTION RESULT:")
print(result.stdout)

if result.stderr:
    print("ERROR/WARNING:")
    print(result.stderr)