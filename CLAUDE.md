# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app (development)
streamlit run app.py

# Run on a server (all interfaces, custom port)
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

## Architecture

Single-page Streamlit app with a sidebar library browser and a main content panel.

```
app.py              # Streamlit UI — sidebar + main panel
services/
  db.py             # SQLite init and connection helper
  converter.py      # PDF → Markdown via pymupdf4llm + artifact cleanup
  library.py        # All DB + filesystem CRUD (papers, folders, comments)
storage/            # Created at runtime
  library.db        # SQLite database
  files/{paper_id}/ # One directory per paper
    paper.pdf
    paper.md
```

### Data model (SQLite)
- **folders** — name; flat list (no sub-folders)
- **papers** — title, filename, folder_id (NULL = root), pdf_path, md_path
- **comments** — paper_id, content, created_at (notes per paper)
- **tags** — name, color (hex); global tag registry
- **paper_tags** — paper_id × tag_id join table

Deleting a folder sets `folder_id = NULL` on its papers (they move to root).
Deleting a paper removes its DB row and its `storage/files/{id}/` directory.

### PDF conversion
`services/converter.py` calls `pymupdf4llm.to_markdown()` for full content extraction (not summarisation), then post-processes to fix hyphenated line-breaks, collapse excess blank lines, strip control characters, and expand ligature glyphs (fi, fl, ff, etc.).

### Session state keys
- `selected_paper_id` — ID of the currently viewed paper (None = welcome screen)
- `show_new_folder` — toggles the new-folder input form in the sidebar
- `pending_delete_paper` / `pending_delete_folder` — ID awaiting confirmation delete
- `editing_title` — bool; shows rename form instead of `st.title()`
- `editing_comment_id` — comment ID currently being edited in-place
- `show_tag_manager` — toggles the tag assignment panel
- `content_search_results` — tuple (query, [paper rows]) from full-text search
