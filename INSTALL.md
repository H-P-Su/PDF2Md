# PDF2Md — Installation Guide

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.14 confirmed working |
| Ollama | latest | for AI summaries and news articles (default backend) |

---

## 1. Install Ollama

Ollama runs language models locally. It is required for the Summary and News Article features (unless you switch to the Claude API backend).

### macOS

Download the one-click installer from **https://ollama.com/download** and run it. Ollama installs as a menu-bar app and starts automatically.

Or via Homebrew:

```bash
brew install ollama
```

### Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Start the server and pull a model

```bash
ollama serve                    # start the server (runs on http://localhost:11434)
                                # not needed on macOS if the menu-bar app is running

ollama pull llama3              # recommended default (~4 GB, one-time download)
```

Other models that work well:

```bash
ollama pull mistral             # faster, slightly less accurate
ollama pull llama3:8b           # smaller, lower memory usage
ollama pull llama3.1            # newer, better instruction following
```

To use a different model, set `PDF2MD_OLLAMA_MODEL` when running the app (see step 5).

Verify Ollama is running:

```bash
curl http://localhost:11434/api/tags   # should return a JSON list of pulled models
```

---

## 2. Install PDF2Md

Unzip the deployment package (or clone the repo), then install Python dependencies:

```bash
unzip pdf2md-*.zip -d PDF2Md
cd PDF2Md

python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

---

## 3. Run the app

```bash
# Local (development)
streamlit run app.py

# Server — accessible on the network
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Open **http://localhost:8501** in your browser.

On first run the app creates:
- `storage/library.db` — SQLite database
- `storage/files/` — PDF Library paper storage
- `storage/Biorxiv_papers/` — bioRxiv paper cache

---

## 4. Configure bioRxiv categories (optional)

By default all bioRxiv categories are active. To limit which categories are fetched, edit `biorxiv_categories.txt` (created on first fetch, or create it manually):

```
# bioRxiv category subscriptions
# Lines starting with # are ignored.

Bioinformatics
Genomics
Neuroscience
# Cancer Biology     ← commented out = inactive
```

You can also manage categories from the **⚙️** menu inside the bioRxiv Updates page.

---

## 5. Environment variables (optional)

All settings have sensible defaults. Override as needed:

```bash
# Use a different Ollama model
PDF2MD_OLLAMA_MODEL=mistral streamlit run app.py

# Use Anthropic Claude instead of Ollama
PDF2MD_BACKEND=claude ANTHROPIC_API_KEY=sk-... streamlit run app.py

# Use a remote Ollama instance
PDF2MD_OLLAMA_HOST=http://192.168.1.10:11434 streamlit run app.py
```

| Variable | Default | Description |
|---|---|---|
| `PDF2MD_BACKEND` | `ollama` | LLM backend: `ollama` or `claude` |
| `PDF2MD_OLLAMA_MODEL` | `llama3` | Ollama model name |
| `PDF2MD_OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `PDF2MD_CLAUDE_MODEL` | `claude-sonnet-4-6` | Claude model (backend=claude only) |
| `ANTHROPIC_API_KEY` | — | Required only when `PDF2MD_BACKEND=claude` |

---

## 6. First-time text-to-speech setup

The Piper voice model (~60 MB) downloads automatically the first time you click **Generate MP3** on any paper. It is saved to `storage/voices/` and reused for all subsequent generations. No action required.

---

## 7. Pre-fetch bioRxiv metadata (optional, recommended)

Run `fetch_biorxiv.py` to cache paper metadata before opening the app. This is especially useful when scheduled as a daily cron job so papers are ready when you open the app.

```bash
# Fetch yesterday (default)
python fetch_biorxiv.py

# Fetch a specific date
python fetch_biorxiv.py --date 2026-03-21

# Fetch the last 7 days (skips already-cached dates)
python fetch_biorxiv.py --days 7

# Fetch a date range
python fetch_biorxiv.py --from 2026-03-01 --to 2026-03-21

# Force re-fetch even if already cached (e.g. after changing categories)
python fetch_biorxiv.py --days 3 --refresh
```

Schedule as a daily cron job (runs at 6 AM):

```bash
crontab -e
# Add:
0 6 * * * cd /path/to/PDF2Md && .venv/bin/python fetch_biorxiv.py >> logs/fetch.log 2>&1
```

See **[examples.md](examples.md)** for more CLI examples.

---

## 8. ML recommendations

The ML scoring pipeline requires no setup — it activates automatically once you have downloaded at least one paper (positive example).

- **Retrain**: open ⚙️ in bioRxiv Updates → **🤖 Retrain model** after downloading new papers or marking papers as ignored.
- **Score**: new papers for any date are scored automatically when you navigate to that date. The ⚙️ **📊 Score stale papers** button rescores all dates with the current model.
- **Negative labels**: click the 🚫 button on any downloaded paper to mark it as a negative example. Retrain after adding labels.

The model upgrades from TF-IDF cosine similarity (cold start, any number of positives) to Logistic Regression automatically once you have 10 or more negative labels.

---

## 9. MCP server (Claude Desktop integration)

The MCP server lets Claude Desktop query your library directly.

Register it by editing `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pdf2md": {
      "command": "/path/to/PDF2Md/.venv/bin/python",
      "args": ["/path/to/PDF2Md/mcp_server.py"]
    }
  }
}
```

Restart Claude Desktop. The library tools will appear in the tool picker.

---

## 10. Running as a background service (macOS / Linux)

```bash
# Start in background, log to app.log
nohup .venv/bin/streamlit run app.py \
  --server.address 0.0.0.0 --server.port 8501 \
  > app.log 2>&1 &

echo $! > app.pid       # save PID

# Stop the server
kill $(cat app.pid)
```

---

## 11. Backing up your library

The entire library lives in the `storage/` directory:

```bash
# Create a backup
tar -czf library-backup-$(date +%Y%m%d).tar.gz storage/

# Restore on a new machine — unpack before starting the app
tar -xzf library-backup-20260322.tar.gz
```

---

## 12. Packaging for deployment

Create a clean zip of source files only (no papers, no database, no venv):

```bash
./package.sh                    # → pdf2md-YYYYMMDD-HHMMSS.zip
./package.sh my-release.zip     # custom filename
```
