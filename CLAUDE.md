# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (prefer uv pip per global CLAUDE.md)
uv pip install -r requirements.txt

# Run the app (development)
streamlit run app.py

# Run on a server (all interfaces, custom port)
streamlit run app.py --server.address 0.0.0.0 --server.port 8501

# Pre-fetch bioRxiv metadata (today's date is now valid)
python fetch_biorxiv.py
python fetch_biorxiv.py --days 7 --refresh

# Generate daily audio digest
python digest_biorxiv.py
python digest_biorxiv.py --date 2026-03-21 --refresh
```

## Architecture

Multi-page Streamlit app (`st.navigation`) with two pages.

```
app.py                      # Entry point — registers pages, calls init_db()
fetch_biorxiv.py            # CLI tool to pre-fetch bioRxiv metadata (today allowed)
digest_biorxiv.py           # CLI tool to generate daily audio digest MP3
pages/
  pdf_library.py            # PDF Library page
  biorxiv_updates.py        # bioRxiv Updates page
services/
  db.py                     # SQLite init and connection helper
  converter.py              # PDF → Markdown via pymupdf4llm + cleanup
  library.py                # PDF Library CRUD (papers, folders, comments, tags)
  biorxiv.py                # bioRxiv API client, metadata storage, download
  summarizer.py             # LLM summarisation (Ollama + Claude backends)
  ml.py                     # ML recommendation pipeline (TF-IDF / LogReg)
  tts.py                    # Offline TTS via Piper
  metadata.py               # Extract authors/DOI/PMID from Markdown
storage/                    # Created at runtime — not in version control
  library.db                # SQLite database
  files/{paper_id}/         # PDF Library papers
    paper.pdf
    paper.md
    summary.md + summary.meta.json
    news.md + news.meta.json
  Biorxiv_papers/{date}/{doi_key}/
    metadata.json           # paper metadata + ml_score, ml_score_version
    paper.pdf
    paper.md
    summary.md + summary.meta.json
    news.md + news.meta.json
  model/
    vectorizer.pkl
    model.pkl
    model_meta.json         # model_version, mode, n_positive, n_negative, trained_at
  voices/                   # Piper TTS voice model (auto-downloaded)
```

## Data model (SQLite — library.db)

- **folders** — id, name, created_at
- **papers** — id, title, filename, folder_id (NULL = root), pdf_path, md_path, created_at
- **comments** — id, paper_id, content, created_at
- **tags** — id, name, color (hex)
- **paper_tags** — paper_id × tag_id

Deleting a folder sets `folder_id = NULL` on its papers (they move to root).
Deleting a paper removes its DB row and its `storage/files/{id}/` directory.

## Key service details

### services/library.py
- `register_external_paper()` — registers a bioRxiv paper (existing file on disk) into the SQLite library. Updates `folder_id` if paper already exists in a different folder.
- `get_or_create_folder(name)` — finds or creates a folder by name; always returns a valid id.
- `get_all_papers()` — returns all papers across all folders (used by main panel browser).

### services/summarizer.py
- `SUMMARIZER_VERSION` — bump when prompts change; written to sidecar `.meta.json` on generation.
- Two functions: `generate_summary()` and `generate_news()`. Each caches to `summary.md` / `news.md` with a `.meta.json` sidecar.
- Default backend: `OllamaBackend` (reads `PDF2MD_BACKEND` env var).

### services/ml.py
- Positive examples: papers with `pdf_path` set and `ml_label != "negative"`.
- Negative examples: `ml_label == "negative"` OR `excluded_from_ml == True`.
- Mode: cosine similarity to centroid when negatives < 10; Logistic Regression otherwise.
- `model_version` integer in `model_meta.json` increments on each `train()` call.
- `ml_score_version` written alongside `ml_score` in each paper's `metadata.json`.
- `score_papers_for_date(date_str)` — scores only papers where `ml_score_version != current model_version`. Called automatically on date load in biorxiv_updates.py.
- `score_all_stale()` — scores all stale papers across all dates.

### services/biorxiv.py
- `PAPERS_DIR = Path("storage/Biorxiv_papers")`
- `doi_to_key(doi)` — sanitises DOI for use as directory name.
- `mark_ignored(date, doi)` — sets `ml_label="negative"` (negative ML example without hiding).
- `mark_excluded(date, doi)` — sets `hidden=True`, `excluded_from_ml=True` (hides paper).
- `reset_download(date, doi)` — deletes PDF, MD, summary, news; clears paths in metadata.

## Session state keys

### pages/pdf_library.py
- `selected_paper_id` — int or None; None shows the library browser
- `lib_search_query` — current search string
- `lib_search_mode` — "Title" or "Full text"
- `lib_folder_filter` — folder_id or None (all folders)
- `lib_sort` — "date" | "title" | "folder"
- `show_new_folder` — unused (new folder now in ⚙️ popover)
- `pending_delete_paper` / `pending_delete_folder` — ID awaiting confirmation
- `editing_title` — bool
- `editing_comment_id` — comment ID in edit mode
- `show_tag_manager` — bool
- `mp3_cache` — {paper_id: bytes | "processing"}
- `generating_summary` / `generating_news` — bool

### pages/biorxiv_updates.py
- `biorxiv_date` — currently selected `date` object
- `biorxiv_cal_year` / `biorxiv_cal_month` — calendar display month
- `biorxiv_categories` — list of active category strings
- `biorxiv_selected` — set of DOIs checked in the current view
- `biorxiv_inited_dates` — set of date strings whose selections have been pre-populated
- `biorxiv_download_queue` — dict {doi: {doi, date_str, title, version}}
- `biorxiv_process_queue` — bool; triggers queue processing on next render
- `biorxiv_filter_downloaded` — bool; filter to downloaded papers only
- `biorxiv_sort_by_score` — bool; sort by ml_score descending

## Query param conventions

- `?date=YYYY-MM-DD` — navigate bioRxiv calendar to a date (set by calendar HTML links)
- `?open_paper=ID` — open a paper in the PDF Library (set by title links)
- `?del_paper=ID` — trigger delete confirmation for a paper (set by trash icon links)
