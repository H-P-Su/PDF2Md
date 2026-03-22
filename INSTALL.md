# PDF2Md — Installation Guide

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.14 confirmed working |
| pip | any | bundled with Python |
| Ollama | latest | for AI summaries (default backend) |

---

## 1. Install Ollama

Download and install from **https://ollama.com** (macOS: one-click installer, Linux: shell script).

Start the Ollama server and pull a model:

```bash
ollama serve                  # start server (runs on http://localhost:11434)
ollama pull llama3            # download default model (~4 GB, first time only)
```

Ollama must be running whenever you use the Summary or News Article features.

---

## 2. Install PDF2Md

Unzip the deployment package (or clone the repo), then install Python dependencies:

```bash
unzip pdf2md-*.zip -d PDF2Md
cd PDF2Md
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 3. Run the app

```bash
# Local (development)
streamlit run app.py

# Server (accessible on the network)
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Open **http://localhost:8501** in your browser.

On first run the app creates:
- `storage/library.db` — SQLite database
- `storage/files/` — paper storage directory

---

## 4. First-time text-to-speech setup

The Piper voice model (~60 MB) is downloaded automatically the first time you click **Generate MP3** on any paper. It is saved to `storage/voices/` and reused for all subsequent generations.

No action is required — this is fully automatic and offline after the initial download.

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

## 6. MCP server (Claude Desktop integration)

The MCP server lets Claude Desktop query your library directly.

**Register it** by editing `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Restart Claude Desktop. The tools will appear in the tool picker.

---

## 7. Running as a background service (macOS)

```bash
# Start in background, log to app.log
nohup .venv/bin/streamlit run app.py \
  --server.address 0.0.0.0 --server.port 8501 \
  > app.log 2>&1 &

echo $! > app.pid     # save PID to stop it later
kill $(cat app.pid)   # stop the server
```

---

## 8. Backing up your library

The entire library lives in the `storage/` directory. Back it up with:

```bash
tar -czf library-backup-$(date +%Y%m%d).tar.gz storage/
```

To restore on a new server, unpack it into the project root before starting the app.

---

## 9. Packaging for deployment

To create a clean zip of source files only (no papers, no database):

```bash
./package.sh                    # → pdf2md-YYYYMMDD-HHMMSS.zip
./package.sh my-release.zip     # custom filename
```
