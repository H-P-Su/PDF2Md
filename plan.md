# PDF2Md — Project Plan

## Status key
- [x] Done
- [-] In progress
- [ ] Planned

---

## Phase 1 — Core app (complete)

- [x] Project scaffolding (`app.py`, `services/`, `storage/`)
- [x] SQLite database schema (folders, papers, comments)
- [x] PDF → Markdown conversion via `pymupdf4llm` (full conversion, not summarisation)
- [x] Post-processing: fix hyphenated line-breaks, strip control chars, expand ligatures
- [x] PDF upload (file picker in sidebar)
- [x] Library sidebar: folder tree, paper list, delete buttons
- [x] Folder management: create, delete (papers demoted to root on delete)
- [x] Paper view: rendered Markdown (read-only) in main panel
- [x] Move paper to a different folder
- [x] Download original PDF from paper view
- [x] Notes / comments section per paper (add, delete)
- [x] `CLAUDE.md`, `README.md`, `requirements.txt`

---

## Phase 2 — Quality & usability (complete)

- [x] Rename paper title in-app (inline form in paper header)
- [x] Search / filter papers by title across the library (sidebar search box)
- [x] Full-text search within paper Markdown content (welcome screen + per-paper expander)
- [x] Tag papers with coloured labels (create, assign, remove; 8 colour choices)
- [x] Sort order options in sidebar (Title A–Z / Date added)
- [x] Edit / update an existing note in-place
- [x] Confirm dialog before deleting a paper or folder
- [x] Duplicate detection on upload (warns if filename already in library)

---

## Phase 3 — AI & audio (complete)

- [x] AI Summary tab — structured summary (overview, findings, full methods, limitations) via LLM
- [x] News Article tab — inverted pyramid rewrite (5 W's) via LLM
- [x] Modular LLM backend (`LLMBackend` protocol); ships `ClaudeBackend` + `OllamaBackend`
- [x] Ollama as default backend (fully local, no API key required)
- [x] AI-generated content cached to disk (`summary.md`, `news.md` per paper)
- [x] Regenerate button for cached summaries
- [x] Text-to-speech: replaced `edge-tts` with Piper (fully offline, no paper text leaves machine)
- [x] MP3 download consolidated into the downloads row alongside PDF and MD
- [x] Paper title displayed from DB; original filename shown as caption

---

## Phase 4 — Integration (complete)

- [x] MCP server (`mcp_server.py`) — 12 read-oriented tools for Claude Desktop / any MCP client
- [x] `package.sh` — clean deployment zip (excludes storage, venv, pycache)
- [x] `INSTALL.md` — step-by-step server setup guide
- [x] `FUTURE_FEATURES.md` — backlog tracking

---

## Phase 5 — Deployment & ops (planned)

- [ ] `Dockerfile` for containerised deployment
- [ ] Configurable storage path via `PDF2MD_STORAGE_DIR` environment variable
- [ ] Basic authentication (single shared password) to protect the server instance
- [ ] Backup/export: zip the entire library (PDFs + MDs + DB) for in-app download
- [ ] Logging: conversion errors and timing written to a log file
- [ ] Re-convert: re-run PDF→MD conversion on an existing paper
- [ ] Batch upload: upload multiple PDFs at once
- [ ] Export selected notes to a single Markdown file

---

## Phase 6 — MCP extensions (planned, see FUTURE_FEATURES.md)

- [ ] Delete paper via MCP
- [ ] Delete folder via MCP
- [ ] Rename paper via MCP

---

## Decisions & constraints

| Decision | Choice | Reason |
|---|---|---|
| UI framework | Streamlit | Rapid development, Python-native, no JS build step |
| PDF extraction | `pymupdf4llm` | Local, no API tokens, good quality for text-based PDFs |
| Database | SQLite | No external service, easy to back up, sufficient for single-user use |
| Storage | Local filesystem | Files and DB live together, simple to move/back up |
| Markdown editable? | No | Conversion output is the source of truth; notes go in comments |
| Folder nesting | One level (flat) | Streamlit `st.expander` doesn't support deep nesting cleanly |
| TTS engine | Piper (local) | Replaced edge-tts; paper text never leaves the machine |
| LLM backend | Ollama (default) | Fully local, no API key; Claude available via env var |
| LLM abstraction | `LLMBackend` Protocol | Any backend with `complete(prompt) -> str` can be plugged in |
| MCP scope | Read-only | Destructive ops (delete, rename) reserved for the UI |
