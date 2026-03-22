# PDF2Md

A personal web library for converting scientific papers (and other PDFs) to Markdown. Upload a PDF, get back clean, readable Markdown. Organise papers into folders, annotate with notes, generate AI summaries, and listen to text-to-speech audio — all running locally.

## Features

- **Convert** — PDFs converted to Markdown via `pymupdf4llm` (fully local, no API tokens). Post-processing cleans up hyphenated line-breaks, ligature glyphs, and other PDF artefacts.
- **Library** — Papers and source PDFs stored together. Organise into folders; move, rename, or delete at any time. Tag papers with coloured labels.
- **Read** — Three reading modes per paper: full Markdown, AI Summary, and News Article rewrite (inverted pyramid, 5 W's).
- **Notes** — Freeform notes per paper, editable in-place.
- **Search** — Title search in the sidebar; full-text content search across all papers.
- **Audio** — Generate MP3 audio from any paper using Piper TTS (fully offline).
- **MCP server** — Expose the library to Claude Desktop or any MCP client via `mcp_server.py`.

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) running locally (for Summary / News Article generation, default backend)

## Setup & installation

See **[INSTALL.md](INSTALL.md)** for the full step-by-step guide, including Ollama setup, MCP server registration, background service, and backup instructions.

Quick start:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ollama pull llama3
streamlit run app.py
```

## Deployment

Run `./package.sh` to create a clean zip of all source files (no papers, no database, no virtual environment) ready to copy to a new server.

---

## Project files

### Root

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI — sidebar library browser, main paper view with Markdown / Summary / News Article tabs, notes, tags, audio, and search |
| `mcp_server.py` | MCP server exposing the library to Claude Desktop or any MCP client. 12 read-oriented tools (list, search, read content, manage comments/tags). No destructive operations. |
| `requirements.txt` | All Python dependencies |
| `package.sh` | Creates a timestamped deployment zip of source files only — excludes `storage/`, `.venv/`, `__pycache__/` |
| `README.md` | This file |
| `CLAUDE.md` | Instructions for Claude Code when working in this repo |
| `FUTURE_FEATURES.md` | Backlog of planned features not yet implemented |
| `plan.md` | Full project roadmap with phase-by-phase status |

### `services/`

| File | Purpose |
|---|---|
| `db.py` | SQLite connection helper and schema initialisation. Creates `storage/library.db` with tables: `folders`, `papers`, `comments`, `tags`, `paper_tags`. |
| `library.py` | All CRUD operations — papers (save, get, search, move, rename, delete), folders (create, delete), comments (add, edit, delete), tags (create, assign, remove). Also manages `storage/files/{id}/` directories on disk. |
| `converter.py` | PDF → Markdown pipeline. Calls `pymupdf4llm.to_markdown()` then post-processes: fixes hyphenated line-breaks, collapses blank lines, strips control characters, expands ligatures (fi, fl, ff, etc.). |
| `summarizer.py` | Modular AI summarisation. Defines `LLMBackend` protocol so any model can be plugged in. Ships `ClaudeBackend` (Anthropic API) and `OllamaBackend` (local, no API key). Active backend selected via `PDF2MD_BACKEND` env var (default: `ollama`). Results cached to `storage/files/{id}/summary.md` and `news.md`. |
| `tts.py` | Text-to-speech using Piper (fully offline). Strips markdown and noise from paper text, synthesises WAV via the `en_US-amy-medium` voice model (auto-downloaded to `storage/voices/` on first use), then encodes to MP3 via `lameenc`. No audio data leaves the machine. |

### `storage/` (runtime — not in version control)

| Path | Contents |
|---|---|
| `storage/library.db` | SQLite database — all metadata |
| `storage/files/{id}/paper.pdf` | Original uploaded PDF |
| `storage/files/{id}/paper.md` | Converted Markdown |
| `storage/files/{id}/summary.md` | Cached AI summary (generated on demand) |
| `storage/files/{id}/news.md` | Cached AI news article (generated on demand) |
| `storage/voices/` | Piper voice model files (downloaded on first TTS use) |

## Limitations & planned work

See [plan.md](plan.md) for the full roadmap. Current known limitations:

- Folders are one level deep (no sub-folders).
- Scanned/image-only PDFs will produce poor Markdown — text must be selectable in the PDF.
- No built-in authentication; restrict access at the network or reverse-proxy level.
