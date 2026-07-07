from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.translation_service import translate_with_views

CASES = [
    (
        "Vivo en Melsungen y trabajo con simulaciones de propagación inalámbrica.",
        "es",
        "en",
        "I live in Melsungen and work with wireless propagation simulations.",
    ),
    (
        "Trabajo con MATLAB, Python y Wireless InSite.",
        "es",
        "hi",
        "मैं मैटलैब, पाइथन और वायरलेस इनसाइट के साथ काम करता हूँ।",
    ),
    (
        "Rajarshi, Amit Shah, Melsungen, Kolkata, and Fraunhofer HHI are mentioned in this sentence.",
        "auto",
        "hi",
        "इस वाक्य में राजर्षि, अमित शाह, मेलसुंगेन, कोलकाता और फ्राउनहोफर एचएचआई का उल्लेख किया गया है।",
    ),
    (
        "The Wireless InSite simulation was post-processed in MATLAB and Python.",
        "en",
        "hi",
        "वायरलेस इनसाइट सिमुलेशन को मैटलैब और पाइथन में पोस्ट-प्रोसेस किया गया था।",
    ),
    (
        "Fraunhofer HHI works with the Karlsruhe Institute of Technology.",
        "en",
        "hi",
        "फ्राउनहोफर एचएचआई कार्ल्सरूहे इंस्टीट्यूट ऑफ टेक्नोलॉजी के साथ काम करता है।",
    ),
    (
        "Ich wohne in Melsungen und komme ursprünglich aus Kolkata.",
        "de",
        "hi",
        "मैं मेलसुंगेन में रहता हूँ और मूल रूप से कोलकाता से आता हूँ।",
    ),
    (
        "i live in melsungen and i work on linguafusion",
        "en",
        "hi",
        "मैं मेलसुंगेन में रहता हूँ और लिंगुआफ्यूज़न पर काम करता हूँ।",
    ),
    (
        "hello this is rajashi i live in melzungen and i work with wireless insight",
        "en",
        "hi",
        "नमस्ते, यह राजर्षि है। मैं मेलसुंगेन में रहता हूँ और वायरलेस इनसाइट के साथ काम करता हूँ।",
    ),
]


def main() -> None:
    failures = []
    for source_text, source_lang, target_lang, expected in CASES:
        result = translate_with_views(source_text, source_lang, target_lang)
        actual = result.get("translated_text")
        if not result.get("ok") or actual != expected:
            failures.append((source_text, result.get("ok"), actual, expected, result.get("error")))
    if failures:
        for source_text, ok, actual, expected, error in failures:
            print("FAILED:", source_text)
            print("ok:", ok, "error:", error)
            print("actual  :", actual)
            print("expected:", expected)
        raise SystemExit(1)
    print("Phase 2 translation validation tests passed")


if __name__ == "__main__":
    main()
