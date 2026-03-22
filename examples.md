# CLI Examples

Shell examples for all command-line-usable functions in PDF2Md.

---

## Running the app

```bash
# Development (local only)
streamlit run app.py

# Network-accessible server
streamlit run app.py --server.address 0.0.0.0 --server.port 8501

# With a different Ollama model
PDF2MD_OLLAMA_MODEL=mistral streamlit run app.py

# With Claude API backend instead of Ollama
PDF2MD_BACKEND=claude ANTHROPIC_API_KEY=sk-... streamlit run app.py

# With a remote Ollama instance
PDF2MD_OLLAMA_HOST=http://192.168.1.10:11434 streamlit run app.py
```

---

## fetch_biorxiv.py — Pre-fetch bioRxiv metadata

Caches paper metadata from the bioRxiv API to `storage/Biorxiv_papers/` without opening the app. Useful for cron jobs so papers are ready when you open the browser.

Skips dates that are already cached unless `--refresh` is passed.

```bash
# Fetch yesterday (default — most common use)
python fetch_biorxiv.py

# Fetch a specific date
python fetch_biorxiv.py --date 2026-03-21

# Fetch the last 3 days (skips already-cached dates)
python fetch_biorxiv.py --days 3

# Fetch a date range
python fetch_biorxiv.py --from 2026-03-01 --to 2026-03-21

# Re-fetch even if already cached (useful after changing categories)
python fetch_biorxiv.py --date 2026-03-21 --refresh

# Re-fetch the last 7 days
python fetch_biorxiv.py --days 7 --refresh
```

### Cron job — fetch yesterday's papers at 6 AM daily

```bash
crontab -e
# Add this line:
0 6 * * * cd /path/to/PDF2Md && .venv/bin/python fetch_biorxiv.py >> logs/fetch.log 2>&1
```

Create the logs directory first:

```bash
mkdir -p /path/to/PDF2Md/logs
```

---

## services/biorxiv.py — bioRxiv service functions

These functions are called by the app and `fetch_biorxiv.py` but can also be used directly in a Python session.

```python
from services.biorxiv import (
    fetch_papers, save_metadata, load_cached_papers,
    load_categories, is_cached, has_pdf, has_markdown,
    download_pdf, extract_keywords, update_keywords_file,
    load_all_downloaded_papers, get_paper_counts_for_month,
    get_downloaded_counts_for_month,
)

# Load configured categories
cats = load_categories()
print(cats)

# Fetch metadata for a date
papers = fetch_papers("2026-03-21", cats)
print(f"{len(papers)} papers found")

# Cache metadata to disk
for p in papers:
    save_metadata(p, "2026-03-21")

# Load cached papers for a date
cached = load_cached_papers("2026-03-21")
print(f"{len(cached)} papers cached")

# Check download status
doi = "10.1101/2026.03.21.123456"
print(is_cached("2026-03-21", doi))    # True/False
print(has_pdf("2026-03-21", doi))      # True/False
print(has_markdown("2026-03-21", doi)) # True/False

# Extract keywords from a paper
kws = extract_keywords(papers[0]["title"], papers[0]["abstract"])
print(kws)

# Get paper counts per day for a month (for the calendar)
counts = get_paper_counts_for_month(2026, 3)  # {day: count}
print(counts)

# Get downloaded counts per day for a month
dl_counts = get_downloaded_counts_for_month(2026, 3)
print(dl_counts)
```

---

## services/ml.py — ML recommendation pipeline

```python
from services.ml import (
    train, score_papers, train_and_score_all,
    score_papers_for_date, score_all_stale,
    load_model_meta, model_exists, load_all_papers,
)

# Check if a trained model exists
print(model_exists())

# Load current model metadata (version, mode, stats)
meta = load_model_meta()
print(meta)
# {'model_version': 3, 'mode': 'similarity', 'n_positive': 12,
#  'n_negative': 2, 'n_unlabeled': 539, 'trained_at': '2026-03-22T...'}

# Train the model on all papers
stats = train()
print(stats)

# Train and score all papers in one step
stats = train_and_score_all()
print(f"Scored {stats['scored']} papers")

# Score only stale papers for a specific date (fast — skips up-to-date scores)
n = score_papers_for_date("2026-03-21")
print(f"Scored {n} papers for 2026-03-21")

# Score all stale papers across all dates
n = score_all_stale()
print(f"Scored {n} stale papers total")

# Load all papers and score them manually
papers = load_all_papers()
scores = score_papers(papers)
for p, s in zip(papers[:5], scores[:5]):
    print(f"{s:.3f}  {p['title'][:60]}")
```

---

## services/summarizer.py — AI summarisation

```python
from services.summarizer import (
    generate_summary, generate_news,
    summary_exists, news_exists,
    load_summary, load_news,
    get_summary_meta, get_news_meta,
    clear_summary, clear_news,
)
from pathlib import Path

md_path = "storage/Biorxiv_papers/2026-03-21/10.1101_2026.03.21.123456/paper.md"
md_text = Path(md_path).read_text(encoding="utf-8")

# Generate a structured summary (cached to summary.md)
summary = generate_summary(md_text, md_path)

# Generate a news article rewrite (cached to news.md)
news = generate_news(md_text, md_path)

# Check existence and load cached versions
if summary_exists(md_path):
    print(load_summary(md_path))
    print(get_summary_meta(md_path))  # {'version': '0.7', 'generated_at': '...'}

if news_exists(md_path):
    print(load_news(md_path))

# Clear cached files (forces regeneration next time)
clear_summary(md_path)
clear_news(md_path)
```

### Using a different backend

```bash
# Use Ollama with mistral
PDF2MD_OLLAMA_MODEL=mistral python -c "
from services.summarizer import generate_summary
from pathlib import Path
md = Path('paper.md').read_text()
print(generate_summary(md, 'paper.md'))
"

# Use the Claude API
PDF2MD_BACKEND=claude ANTHROPIC_API_KEY=sk-... python -c "
from services.summarizer import generate_summary
from pathlib import Path
md = Path('paper.md').read_text()
print(generate_summary(md, 'paper.md'))
"
```

---

## services/converter.py — PDF to Markdown

```python
from services.converter import convert_pdf_to_markdown

# Convert a PDF file to clean Markdown
md_text = convert_pdf_to_markdown("paper.pdf")
print(md_text[:500])
```

---

## Backup and restore

```bash
# Backup the entire library (papers, database, bioRxiv cache, ML model)
tar -czf library-backup-$(date +%Y%m%d).tar.gz storage/

# Backup the ML model only
tar -czf model-backup-$(date +%Y%m%d).tar.gz storage/model/

# Restore
tar -xzf library-backup-20260322.tar.gz

# Check backup size
du -sh library-backup-*.tar.gz
```

---

## Deployment packaging

```bash
# Create a source-only zip (no storage/, no .venv/, no __pycache__)
./package.sh

# Custom output filename
./package.sh pdf2md-release-1.0.zip
```
