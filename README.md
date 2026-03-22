# PDF2Md

A personal web library for scientific papers and PDFs. Two integrated apps in one:

- **PDF Library** — upload PDFs, convert to Markdown, organise, annotate, and generate AI summaries
- **bioRxiv Updates** — browse daily preprints, download papers, and get ML-ranked recommendations based on your reading history

All processing runs locally. No data leaves your machine unless you choose the Claude API backend.

## Features

### PDF Library
- **Convert** — PDFs → clean Markdown via `pymupdf4llm`. Post-processing fixes hyphenated line-breaks, ligature glyphs, and other artefacts.
- **Library browser** — full-width table with title search (title or full-text), folder filter, sort by date/title/folder. Folder and new-folder management in the ⚙️ menu.
- **Organise** — folders, coloured tags, move, rename, delete.
- **Read** — three tabs per paper: Markdown, AI Summary, News Article rewrite.
- **Notes** — freeform annotations per paper, editable in-place.
- **Audio** — generate MP3 from any paper via Piper TTS (fully offline).
- **Sync** — one-click registration of bioRxiv downloads into the library.
- **MCP server** — expose the library to Claude Desktop via `mcp_server.py`.

### bioRxiv Updates
- **Calendar** — click any past day to view its papers; green dates indicate downloads.
- **Fetch** — pull paper metadata from the bioRxiv API for any date and configured categories.
- **Download queue** — select papers, queue across date navigation, process in batch.
- **Phased pipeline** — PDF → Markdown → keywords → AI summary/news (each phase independently cacheable).
- **ML recommendations** — TF-IDF cosine similarity (cold start) upgrading to Logistic Regression as you label. Papers you download are positive examples; click 🚫 Ignore on any paper for a negative label.
- **Auto-scoring** — new papers are scored against the current model automatically when a date is loaded; only stale scores are recomputed.
- **Pre-fetch CLI** — `fetch_biorxiv.py` can be scheduled via cron to cache metadata before you open the app.

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.14 confirmed working |
| Ollama | latest | for AI summaries/news (default LLM backend) |

See **[INSTALL.md](INSTALL.md)** for the full step-by-step guide.

## Quick start

```bash
# 1. Install Ollama and pull a model
ollama pull llama3

# 2. Create and activate a virtual environment
python -m venv .venv && source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
streamlit run app.py
```

Open **http://localhost:8501**.

See **[examples.md](examples.md)** for CLI command examples.

---

## Project files

### Root

| File | Purpose |
|---|---|
| `app.py` | Streamlit entry point — registers pages and initialises the database |
| `fetch_biorxiv.py` | CLI tool to pre-fetch and cache bioRxiv metadata (schedule with cron) |
| `mcp_server.py` | MCP server exposing the PDF library to Claude Desktop. 12 read-oriented tools. |
| `biorxiv_categories.txt` | Active bioRxiv category subscriptions (one per line; `#` to comment out) |
| `requirements.txt` | Python dependencies |
| `package.sh` | Creates a timestamped deployment zip (source only — no storage, no venv) |
| `examples.md` | Shell examples for all CLI-usable functions |
| `plan.md` | Full project roadmap with phase-by-phase status |
| `FUTURE_FEATURES.md` | Backlog of features not yet implemented |

### `pages/`

| File | Purpose |
|---|---|
| `pages/pdf_library.py` | PDF Library page — upload, browse, paper view with tabs, notes, tags, audio |
| `pages/biorxiv_updates.py` | bioRxiv Updates page — calendar, fetch, download queue, ML scoring, summaries |

### `services/`

| File | Purpose |
|---|---|
| `db.py` | SQLite connection helper and schema initialisation (`storage/library.db`) |
| `library.py` | CRUD for papers, folders, comments, tags. Manages `storage/files/{id}/` on disk. Also handles bioRxiv paper registration (`register_external_paper`, `get_or_create_folder`). |
| `converter.py` | PDF → Markdown pipeline via `pymupdf4llm` with post-processing cleanup |
| `summarizer.py` | Modular AI summarisation. `LLMBackend` protocol with `OllamaBackend` (default) and `ClaudeBackend`. Results cached with versioned sidecar `.meta.json` files. |
| `biorxiv.py` | bioRxiv API client — fetch, cache, download PDFs, extract keywords, manage metadata. |
| `ml.py` | ML recommendation pipeline. TF-IDF cosine similarity (cold start) → Logistic Regression (once 10+ negative labels). Versioned model artefacts in `storage/model/`. |
| `tts.py` | Offline text-to-speech via Piper (`en_US-amy-medium`). Voice model auto-downloaded to `storage/voices/` on first use. |
| `metadata.py` | Extracts authors, DOI, PMID from Markdown text. |

### `storage/` (runtime — not in version control)

| Path | Contents |
|---|---|
| `storage/library.db` | SQLite database |
| `storage/files/{id}/` | Uploaded PDFs and their Markdown, summary, and news files |
| `storage/Biorxiv_papers/{date}/{doi}/` | bioRxiv paper files (PDF, Markdown, summary, news, metadata.json) |
| `storage/model/` | ML model artefacts (vectorizer.pkl, model.pkl, model_meta.json) |
| `storage/voices/` | Piper TTS voice model files |

## LLM backends

The summariser and news-article generator support two backends, selected via the `PDF2MD_BACKEND` environment variable:

| Backend | Variable | Requirements |
|---|---|---|
| Ollama (default) | `PDF2MD_BACKEND=ollama` | Ollama running locally |
| Claude API | `PDF2MD_BACKEND=claude` | `ANTHROPIC_API_KEY` set |

## Limitations

- Folders are one level deep (no sub-folders).
- Scanned/image-only PDFs produce poor Markdown — text must be selectable in the PDF.
- No built-in authentication; restrict access at the network or reverse-proxy level.
- ML recommendations require at least one downloaded paper before scoring begins.
