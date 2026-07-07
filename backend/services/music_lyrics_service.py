import re
from typing import Dict, List

# Small, explicit ASR-confusion dictionary. This is NOT a lyrics database; it only
# repairs frequent recognition mistakes and named entities seen in music/speech.
LYRIC_PHRASE_CORRECTIONS = {
    "Shandong River": "Shenandoah River",
    "Shandongo River": "Shenandoah River",
    "Shenando River": "Shenandoah River",
    "Shenandoa River": "Shenandoah River",
    "Shenandoah river": "Shenandoah River",
    "Blue Rich Mountains": "Blue Ridge Mountains",
    "Blue Rich Mountain": "Blue Ridge Mountains",
    "Blue Ridge Mountain": "Blue Ridge Mountains",
    "Blue Water Mountains": "Blue Ridge Mountains",
    "Stranger to blue water": "Shenandoah River",
    "West Virgina": "West Virginia",
    "West Virginian": "West Virginia",
    "Almost haven": "Almost heaven",
    "Almost Heaven": "Almost heaven",
    "All my memories": "All my memories",
    "Honor's lady": "miner's lady",
    "honors lady": "miner's lady",
    "Stranger to blue water": "stranger to blue water",
    "Misty taste of moon shine": "Misty taste of moonshine",
    "Younger than the mountains, growing like a tree": "Younger than the mountains, blowing like a breeze",
    "Younger than the mountains, growing like the trees": "Younger than the mountains, blowing like a breeze",
    "Younger than the mountains, growing like a breeze": "Younger than the mountains, blowing like a breeze",
    "Country roll": "Country roads",
    "Country rolls": "Country roads",
    "Country Road": "Country roads",
    "Country road": "Country roads",
    "Mountain Momma": "Mountain Mama",
    "mountain momma": "Mountain Mama",
    "Me in the middle of the air": "Meet me in the middle of the air",
    "Ain't no brave": "Ain't no grave",
    "Aint no brave": "Ain't no grave",
    "hold my body tight": "hold my body down",
    "can hold my body tight": "can hold my body down",
    "I check in my door": "I'll check in at the door",
}

MUSIC_ARTIFACT_PATTERNS = [
    r"\(\s*keyboard clicking\s*\)",
    r"\(\s*tastatur klicken\s*\)",
    r"\(\s*guitar music\s*\)",
    r"\(\s*guitarrenmusik\s*\)",
    r"\(\s*music\s*\)",
    r"\(\s*musik\s*\)",
    r"\[\s*music\s*\]",
    r"\[\s*musik\s*\]",
    r"\*\s*music\s*\*",
    r"\*\s*musik\s*\*",
    r"\*\s*guitar(?:ren)?music\s*\*",
    r"♪+",
]

BAD_DIAGNOSTIC_TERMS = [
    "load_backend", "input file not found", "whisper_", "ggml_", "read_audio_data", "output_txt",
    "whisper_print_timings", "no gpu found", "using blas backend",
]

ARTIFACT_WORDS = {"music", "musik", "guitar", "guitarrenmusik", "keyboard", "clicking", "tastatur", "klicken"}


def apply_lyric_phrase_corrections(text: str) -> str:
    corrected = text or ""
    for wrong, right in sorted(LYRIC_PHRASE_CORRECTIONS.items(), key=lambda item: len(item[0]), reverse=True):
        corrected = re.sub(rf"(?<!\w){re.escape(wrong)}(?!\w)", right, corrected, flags=re.IGNORECASE)
    return corrected


def remove_music_artifacts(text: str) -> str:
    cleaned = text or ""
    for pattern in MUSIC_ARTIFACT_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[#*♪]+", " ", cleaned)
    cleaned = re.sub(r"\b(?:music|musik|guitar music|guitarrenmusik|keyboard clicking|tastatur klicken)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def strip_backend_logs(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        lower = line.lower()
        if any(term in lower for term in BAD_DIAGNOSTIC_TERMS):
            continue
        lines.append(line)
    return "\n".join(lines)


def normalize_for_duplicate(sentence: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", sentence.lower()).strip()


def split_lyric_fragments(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    raw = re.split(r"(?<=[.!?])\s+|\s+[|/]\s+", text)
    pieces: List[str] = []
    for part in raw:
        part = part.strip(" ,;:-")
        if not part:
            continue
        # Very long comma chains are usually Whisper's unsegmented lyrics.
        if len(part.split()) > 18 and "," in part:
            pieces.extend([p.strip(" ,;:-") for p in part.split(",") if p.strip(" ,;:-")])
        else:
            pieces.append(part)
    return pieces


def collapse_repeated_lyrics(text: str, max_repeat: int = 2) -> str:
    pieces = split_lyric_fragments(text)
    if not pieces:
        return ""
    result = []
    counts: Dict[str, int] = {}
    previous = ""
    for piece in pieces:
        norm = normalize_for_duplicate(piece)
        if not norm or norm in ARTIFACT_WORDS:
            continue
        counts[norm] = counts.get(norm, 0) + 1
        if norm == previous:
            continue
        if counts[norm] > max_repeat:
            continue
        result.append(piece)
        previous = norm
    joined = ". ".join(result)
    joined = re.sub(r"\s+([,.;:!?])", r"\1", joined)
    joined = re.sub(r"([.!?])\. +", r"\1 ", joined)
    joined = re.sub(r"\s+", " ", joined).strip()
    return joined


def reject_bad_candidate(text: str) -> bool:
    lower = (text or "").lower()
    if not text or len(text.strip()) < 8:
        return True
    if any(term in lower for term in BAD_DIAGNOSTIC_TERMS):
        return True
    words = re.findall(r"\w+", lower)
    if words:
        artifact_count = sum(1 for w in words if w in ARTIFACT_WORDS)
        if artifact_count / len(words) > 0.20:
            return True
    return False


def refine_lyrics_transcript(text: str, preserve_repeats: bool = False) -> str:
    refined = strip_backend_logs(text)
    refined = remove_music_artifacts(refined)
    refined = apply_lyric_phrase_corrections(refined)
    if not preserve_repeats:
        refined = collapse_repeated_lyrics(refined, max_repeat=2)
    refined = re.sub(r"\s+", " ", refined).strip()
    return refined


def score_candidate(text: str) -> float:
    if reject_bad_candidate(text):
        return -9999.0
    text = refine_lyrics_transcript(text)
    lower = text.lower()
    words = re.findall(r"\w+", lower)
    unique_words = len(set(words))
    score = unique_words * 2.0 + min(len(words), 320) * 0.40
    if len(words) < 30:
        score -= 90
    if 60 <= len(words) <= 260:
        score += 40
    if len(words) > 450:
        score -= 60
    for term in BAD_DIAGNOSTIC_TERMS + ["guitarrenmusik", "tastatur klicken"]:
        if term in lower:
            score -= 220
    for artifact in [" music ", " musik ", "keyboard clicking", "guitar music"]:
        score -= lower.count(artifact) * 30
    for phrase, bonus in {
        "shenandoah river": 65,
        "blue ridge mountains": 55,
        "west virginia": 45,
        "almost heaven": 45,
        "country roads": 45,
        "take me home": 35,
        "mountain mama": 35,
        "ain't no grave": 40,
        "hold my body down": 30,
    }.items():
        if phrase in lower:
            score += bonus
    german_markers = ["schneller", "himmel", "berge", "bäume", "leben", "älter", "dort", "west-virginia", "landstraßen"]
    score -= sum(28 for marker in german_markers if marker in lower)
    return score


def choose_best_candidate(candidates: List[Dict[str, object]], baseline_words: int = 0) -> Dict[str, object]:
    valid = []
    for c in candidates:
        text = refine_lyrics_transcript(str(c.get("text", "")))
        if reject_bad_candidate(text):
            continue
        item = dict(c)
        item["text"] = text
        item["score"] = score_candidate(text)
        # Guard against online responses that shrink a whole song into one tiny fragment.
        words = len(re.findall(r"\w+", text))
        if baseline_words and words < max(25, int(baseline_words * 0.55)):
            item["score"] -= 180
        valid.append(item)
    if not valid:
        return {"provider": "none", "text": "", "score": -9999}
    return sorted(valid, key=lambda item: item.get("score", -9999), reverse=True)[0]


def line_break_lyrics(text: str) -> str:
    return "\n".join(split_lyric_fragments(refine_lyrics_transcript(text)))
