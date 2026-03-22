"""
Summarizer service.

Backends
--------
Any object that implements ``LLMBackend`` can be used:

    class LLMBackend(Protocol):
        def complete(self, prompt: str) -> str: ...

Built-in backends
-----------------
- ClaudeBackend   – Anthropic Claude (requires ANTHROPIC_API_KEY)
- OllamaBackend   – local Ollama instance (no API key; requires Ollama running)

Active backend
--------------
Set the ``PDF2MD_BACKEND`` environment variable:

    PDF2MD_BACKEND=claude    # default
    PDF2MD_BACKEND=ollama

Or pass a backend instance directly to generate_summary / generate_news.

Adding a new backend
--------------------
Implement the LLMBackend protocol and either pass it explicitly or extend
get_default_backend() to recognise a new PDF2MD_BACKEND value.
"""

import json
import os
import urllib.request
from pathlib import Path
from typing import Protocol, runtime_checkable

_MAX_CHARS = 100_000  # ~25 k tokens; covers virtually all academic papers

_SUMMARY_PROMPT = """\
Summarize the following academic paper in structured markdown.
Include:
- A 2–3 sentence overview
- Key findings and contributions (bullet points)
- Methods — cover all methods used in full detail: experimental design, \
data collection, instruments, models, algorithms, statistical analyses, \
and any tools or software mentioned
- Limitations and future work

Paper:

{content}"""

_NEWS_PROMPT = """\
Rewrite the following academic paper as a news article using the inverted \
pyramid structure (most important information first). Answer the 5 W's: \
Who, What, When, Where, Why (and How). Write for a general audience. \
Use short paragraphs and plain language — avoid academic jargon. \
Lead with the single most newsworthy finding.

Paper:

{content}"""


# ── Protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class LLMBackend(Protocol):
    """Minimal interface any LLM backend must satisfy."""

    def complete(self, prompt: str) -> str:
        """Send *prompt* to the model and return the response text."""
        ...


# ── Built-in backends ─────────────────────────────────────────────────────────

class ClaudeBackend:
    """Anthropic Claude via the official SDK. Requires ANTHROPIC_API_KEY."""

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 2048):
        self.model = model
        self.max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def complete(self, prompt: str) -> str:
        response = self._get_client().messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text


class OllamaBackend:
    """Local Ollama instance. No API key required.

    Ollama must be running (``ollama serve``) and the chosen model pulled
    (``ollama pull <model>``) before use.
    """

    def __init__(
        self,
        model: str = "llama3",
        host: str = "http://localhost:11434",
        max_tokens: int = 2048,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.max_tokens = max_tokens

    def complete(self, prompt: str) -> str:
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": self.max_tokens},
        }).encode()

        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return data["response"]


# ── Default backend selection ─────────────────────────────────────────────────

def get_default_backend() -> LLMBackend:
    """Return the backend selected by PDF2MD_BACKEND (default: claude)."""
    name = os.environ.get("PDF2MD_BACKEND", "ollama").lower()
    if name == "ollama":
        model = os.environ.get("PDF2MD_OLLAMA_MODEL", "llama3")
        host  = os.environ.get("PDF2MD_OLLAMA_HOST", "http://localhost:11434")
        return OllamaBackend(model=model, host=host)
    if name == "claude":
        model = os.environ.get("PDF2MD_CLAUDE_MODEL", "claude-sonnet-4-6")
        return ClaudeBackend(model=model)
    raise ValueError(
        f"Unknown PDF2MD_BACKEND={name!r}. "
        "Supported values: 'claude', 'ollama'."
    )


# ── Disk-cache helpers ────────────────────────────────────────────────────────

def _summary_path(md_path: str) -> Path:
    return Path(md_path).parent / "summary.md"


def _news_path(md_path: str) -> Path:
    return Path(md_path).parent / "news.md"


def summary_exists(md_path: str) -> bool:
    return _summary_path(md_path).exists()


def news_exists(md_path: str) -> bool:
    return _news_path(md_path).exists()


def load_summary(md_path: str) -> str:
    return _summary_path(md_path).read_text(encoding="utf-8")


def load_news(md_path: str) -> str:
    return _news_path(md_path).read_text(encoding="utf-8")


def clear_summary(md_path: str) -> None:
    p = _summary_path(md_path)
    if p.exists():
        p.unlink()


def clear_news(md_path: str) -> None:
    p = _news_path(md_path)
    if p.exists():
        p.unlink()


# ── Public generation functions ───────────────────────────────────────────────

def generate_summary(
    md_text: str,
    md_path: str,
    backend: LLMBackend | None = None,
) -> str:
    """Generate a structured summary and cache it to disk."""
    b = backend or get_default_backend()
    result = b.complete(_SUMMARY_PROMPT.format(content=md_text[:_MAX_CHARS]))
    _summary_path(md_path).write_text(result, encoding="utf-8")
    return result


def generate_news(
    md_text: str,
    md_path: str,
    backend: LLMBackend | None = None,
) -> str:
    """Generate a news-article rewrite and cache it to disk."""
    b = backend or get_default_backend()
    result = b.complete(_NEWS_PROMPT.format(content=md_text[:_MAX_CHARS]))
    _news_path(md_path).write_text(result, encoding="utf-8")
    return result
