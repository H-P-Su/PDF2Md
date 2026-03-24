import io
import re
import wave
from pathlib import Path


# Section headings that mark the end of the readable body
_STOP_SECTIONS = {
    "references", "bibliography", "works cited",
    "acknowledgements", "acknowledgments", "appendix",
    "supplementary material", "supplementary materials",
    "conflict of interest", "competing interests",
    "funding", "author contributions",
}

_EMAIL_RE   = re.compile(r'\S+@\S+\.\S+')
_URL_RE     = re.compile(r'https?://\S+|www\.\S+')
_DOI_RE     = re.compile(r'\b(doi|DOI)[:\s]|\bdoi\.org/')
_CITATION_RE = re.compile(r'\[\d+(?:[,;\s]\d+)*\]')
_FIGURE_RE  = re.compile(r'^(fig\.?|figure|table|algorithm|listing|scheme|chart)\s*\d', re.IGNORECASE)
_HEADER_NUM_RE = re.compile(r'^\d+(\.\d+)*\s')   # "1.2 Introduction" style
# Lines that are mostly non-alphabetic (equations, data rows, etc.)
_MOSTLY_NONALPHA_RE = re.compile(r'^[^a-zA-Z]{0,3}$')

# Voice model config
_VOICES_DIR = Path("storage/voices")
_VOICE_NAME = "en_US-amy-medium"
_MODEL_BASE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    "/en/en_US/amy/medium"
)


def _ensure_voice_model() -> Path:
    """Download the Piper voice model to storage/voices/ if not already present."""
    _VOICES_DIR.mkdir(parents=True, exist_ok=True)
    onnx_path = _VOICES_DIR / f"{_VOICE_NAME}.onnx"
    json_path = _VOICES_DIR / f"{_VOICE_NAME}.onnx.json"

    if not onnx_path.exists():
        import urllib.request
        urllib.request.urlretrieve(
            f"{_MODEL_BASE_URL}/{_VOICE_NAME}.onnx", onnx_path
        )
        urllib.request.urlretrieve(
            f"{_MODEL_BASE_URL}/{_VOICE_NAME}.onnx.json", json_path
        )

    return onnx_path


def _clean_for_tts(md_text: str) -> str:
    """Return plain prose text suitable for TTS, stripping metadata and noise."""
    lines = md_text.splitlines()

    # Locate where to stop (references / acknowledgements / appendix)
    stop_idx = len(lines)
    for i, line in enumerate(lines):
        bare = line.strip().lstrip('#').strip().lower()
        if bare in _STOP_SECTIONS:
            stop_idx = i
            break

    cleaned = []
    for line in lines[:stop_idx]:
        s = line.strip()

        # Skip blank lines (preserve paragraph rhythm)
        if not s:
            cleaned.append('')
            continue

        # Skip lines with emails, URLs, or DOIs
        if _EMAIL_RE.search(s) or _URL_RE.search(s) or _DOI_RE.search(s):
            continue

        # Skip figure / table captions
        if _FIGURE_RE.match(s):
            continue

        # Skip lines that look like author affiliations:
        # typically start with a superscript digit or are wrapped in parentheses/brackets
        if re.match(r'^[\d†‡§¶∗*]+\s+[A-Z]', s):
            continue

        # Skip lines that are almost entirely non-alphabetic (equations, etc.)
        if len(s) < 40 and len(re.findall(r'[a-zA-Z]', s)) / max(len(s), 1) < 0.4:
            continue

        # --- Strip markdown formatting ---
        # Remove heading markers
        s = re.sub(r'^#{1,6}\s*', '', s)
        # Bold / italic
        s = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', s)
        s = re.sub(r'_{1,3}(.*?)_{1,3}', r'\1', s)
        # Inline code / code fences
        s = re.sub(r'`[^`]*`', '', s)
        s = re.sub(r'^```.*', '', s)
        # Links  [text](url)  →  text
        s = re.sub(r'!\[[^\]]*\]\([^\)]*\)', '', s)   # images first
        s = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', s)
        # Citation brackets [1], [2,3]
        s = _CITATION_RE.sub('', s)
        # Footnote markers [^n]
        s = re.sub(r'\[\^[^\]]+\]', '', s)
        # Horizontal rules
        s = re.sub(r'^[-*_]{3,}$', '', s)

        s = s.strip()
        if s:
            cleaned.append(s)

    return '\n'.join(cleaned)


_WORDS_PER_MINUTE = 150
_DIGEST_MAX_WORDS = _WORDS_PER_MINUTE * 20  # 3 000 words ≈ 20 minutes


def _first_n_words(text: str, n: int) -> str:
    words = text.split()
    if len(words) <= n:
        return text
    return " ".join(words[:n]) + "."


def build_daily_digest_script(date_str: str, papers: list[dict]) -> str:
    """Assemble a spoken-word script for *papers*, fitting within ~20 minutes.

    For each paper the best available content is used in priority order:
    news.md → summary.md → abstract.  The per-paper word budget is split
    evenly from the remaining budget after overhead text is accounted for.
    """
    from datetime import date as _date
    from pathlib import Path

    d = _date.fromisoformat(date_str)
    day_label = d.strftime("%A, %B %-d, %Y")
    n = len(papers)
    categories = list(dict.fromkeys(p.get("category", "") for p in papers))

    intro_lines = [
        f"bioRxiv digest for {day_label}.",
        f"{n} paper{'s' if n != 1 else ''} across "
        f"{len(categories)} {'category' if len(categories) == 1 else 'categories'}.",
        "",
    ]

    # Reserve words for overhead: intro + ~12 words per paper (title / author header)
    overhead = len(" ".join(intro_lines).split()) + n * 12
    per_paper = max(30, (_DIGEST_MAX_WORDS - overhead) // n) if n else 0

    lines = list(intro_lines)
    current_cat = None
    for paper in papers:
        cat = paper.get("category", "Uncategorized")
        if cat != current_cat:
            current_cat = cat
            lines += ["", cat + ".", ""]

        title = paper.get("title", "Untitled")
        authors = paper.get("authors", "")
        first_author = (
            authors.split(";")[0].strip().split(",")[0].strip()
            if authors else ""
        )

        # Best available content
        content = ""
        md_path = paper.get("md_path", "")
        if md_path:
            paper_dir = Path(md_path).parent
            for fname in ("news.md", "summary.md"):
                candidate = paper_dir / fname
                if candidate.exists():
                    content = candidate.read_text(encoding="utf-8")
                    break
        if not content:
            content = paper.get("abstract", "")

        content = _first_n_words(_clean_for_tts(content), per_paper)

        header = f"{title}."
        if first_author:
            header += f" By {first_author}."
        lines += [header, content, ""]

    return "\n".join(lines)


def daily_digest_mp3(date_str: str, papers: list[dict]) -> bytes:
    """Return MP3 bytes for the daily digest, generating and caching on first call.

    The file is stored at ``storage/Biorxiv_papers/{date_str}/digest.mp3``.
    Delete the file to force regeneration.
    """
    cache_path = Path("storage/Biorxiv_papers") / date_str / "digest.mp3"
    if cache_path.exists():
        return cache_path.read_bytes()

    script = build_daily_digest_script(date_str, papers)
    mp3 = markdown_to_mp3(script)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(mp3)
    return mp3


def markdown_to_mp3(md_text: str, voice: str = "en_US-amy-medium") -> bytes:
    """Convert markdown paper text to MP3 bytes using Piper (fully local/offline)."""
    from piper import PiperVoice
    import lameenc

    clean = _clean_for_tts(md_text)
    model_path = _ensure_voice_model()

    piper_voice = PiperVoice.load(str(model_path))

    # Synthesize to an in-memory WAV buffer
    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wav_file:
        piper_voice.synthesize_wav(clean, wav_file)

    # Read WAV parameters and raw PCM frames
    wav_buf.seek(0)
    with wave.open(wav_buf, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        pcm_frames = wav_file.readframes(wav_file.getnframes())

    # Encode PCM → MP3 using lameenc (pure Python, no system deps)
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(128)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(channels)
    encoder.set_quality(2)  # 2 = highest quality

    return bytes(encoder.encode(pcm_frames) + encoder.flush())
