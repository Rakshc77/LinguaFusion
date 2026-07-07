from backend.services.piper_service import speak_to_file

test_text = """
Krüger.
für.
größer.
Mädchen.
Überprüfung.
später.
regelmäßigen.
"""

path = speak_to_file(
    test_text,
    "de",
    "umlaut_test.wav"
)

print(f"Generated: {path}")