"""bioRxiv API service — categories, paper fetching, download, and storage."""

import json
import re
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

CATEGORIES_FILE = Path("biorxiv_categories.txt")
PAPERS_DIR      = Path("storage/Biorxiv_papers")
KEYWORDS_FILE   = PAPERS_DIR / "keywords.json"
API_BASE        = "https://api.biorxiv.org/details/biorxiv"

ALL_CATEGORIES = [
    "Animal Behavior and Cognition",
    "Biochemistry",
    "Bioengineering",
    "Bioinformatics",
    "Biophysics",
    "Cancer Biology",
    "Cell Biology",
    "Clinical Trials",
    "Developmental Biology",
    "Ecology",
    "Epidemiology",
    "Evolutionary Biology",
    "Genetics",
    "Genomics",
    "Immunology",
    "Microbiology",
    "Molecular Biology",
    "Neuroscience",
    "Paleontology",
    "Pathology",
    "Pharmacology and Toxicology",
    "Physiology",
    "Plant Biology",
    "Scientific Communication and Education",
    "Synthetic Biology",
    "Systems Biology",
    "Zoology",
]

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "this",
    "that", "these", "those", "we", "our", "us", "they", "their", "it",
    "its", "not", "also", "both", "such", "than", "more", "most", "all",
    "each", "which", "who", "how", "when", "where", "why", "what",
    "into", "through", "during", "before", "after", "between", "here",
    "there", "then", "so", "if", "while", "because", "since", "thus",
    "therefore", "however", "moreover", "whereas", "whether",
    "using", "used", "use", "show", "shows", "showed", "shown",
    "suggest", "suggests", "study", "found", "find", "data",
    "analysis", "approach", "method", "methods", "model",
    "significant", "significantly", "important", "novel", "new",
    "based", "high", "low", "large", "small", "different", "same",
    "two", "three", "first", "second", "one", "many", "several",
    "present", "previous", "further", "including", "following",
    "result", "results", "paper", "work", "provide", "provides",
    "demonstrate", "demonstrates", "identify", "identified",
    "well", "known", "key", "role", "function", "associated", "related",
    "respectively", "compared", "increased", "decreased", "higher", "lower",
    "here", "whether", "their", "between", "within", "across", "among",
    "via", "upon", "while", "although", "however", "therefore", "thus",
})


# ── Categories ────────────────────────────────────────────────────────────────

def load_categories() -> list[str]:
    """Return active (non-commented) categories from the config file."""
    if not CATEGORIES_FILE.exists():
        return list(ALL_CATEGORIES)
    active = []
    for line in CATEGORIES_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            active.append(stripped)
    return active


def save_categories(active: list[str]) -> None:
    """Rewrite the categories file, commenting out inactive categories."""
    lines = [
        "# bioRxiv category subscriptions",
        "# One category per line. Lines starting with # are ignored.",
        "# Changes here take effect the next time the app fetches papers.",
        "",
    ]
    for cat in ALL_CATEGORIES:
        prefix = "" if cat in active else "# "
        lines.append(f"{prefix}{cat}")
    lines.append("")
    CATEGORIES_FILE.write_text("\n".join(lines), encoding="utf-8")


def category_to_param(category: str) -> str:
    """Convert display name to API query parameter value."""
    return category.lower().replace(" ", "_")


# ── Storage helpers ───────────────────────────────────────────────────────────

def doi_to_key(doi: str) -> str:
    """Sanitise a DOI into a safe directory name."""
    return doi.replace("/", "_").replace(":", "_")


def _paper_dir(date: str, doi: str) -> Path:
    return PAPERS_DIR / date / doi_to_key(doi)


def is_cached(date: str, doi: str) -> bool:
    return (_paper_dir(date, doi) / "metadata.json").exists()


def has_pdf(date: str, doi: str) -> bool:
    return (_paper_dir(date, doi) / "paper.pdf").exists()


def has_markdown(date: str, doi: str) -> bool:
    return (_paper_dir(date, doi) / "paper.md").exists()


# ── API fetch ─────────────────────────────────────────────────────────────────

def _api_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def fetch_papers(date: str, categories: list[str]) -> list[dict]:
    """Fetch all papers for a date across categories. Deduplicates by DOI."""
    seen: set[str] = set()
    papers: list[dict] = []

    for cat in categories:
        param = category_to_param(cat)
        cursor = 0
        while True:
            data = _api_get(
                f"{API_BASE}/{date}/{date}/{cursor}/json?category={param}"
            )
            msg        = data["messages"][0]
            collection = data.get("collection", [])
            for paper in collection:
                doi = paper["doi"]
                if doi not in seen:
                    seen.add(doi)
                    papers.append(paper)
            cursor += len(collection)
            total = int(msg.get("total") or msg.get("count") or 0)
            if cursor >= total or not collection:
                break

    papers.sort(key=lambda p: (p["category"], p["title"]))
    return papers


# ── Metadata persistence ──────────────────────────────────────────────────────

def save_metadata(paper: dict, date: str) -> Path:
    """Save paper metadata as JSON. Returns the paper directory."""
    d = _paper_dir(date, paper["doi"])
    d.mkdir(parents=True, exist_ok=True)
    meta = {
        "doi":            paper["doi"],
        "title":          paper["title"],
        "authors":        paper["authors"],
        "author_corresponding":             paper.get("author_corresponding", ""),
        "author_corresponding_institution": paper.get("author_corresponding_institution", ""),
        "category":       paper["category"],
        "abstract":       paper["abstract"],
        "keywords":       [],
        "version":        paper["version"],
        "type":           paper.get("type", ""),
        "license":        paper.get("license", ""),
        "date":           paper["date"],
        "published":      paper.get("published", "NA"),
        "jatsxml":        paper.get("jatsxml", ""),
        "pdf_path":       "",
        "md_path":        "",
        "fetched_at":     datetime.utcnow().isoformat() + "Z",
    }
    (d / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return d


def load_metadata(date: str, doi: str) -> dict | None:
    """Load metadata.json for a single paper, or None if not cached."""
    path = _paper_dir(date, doi) / "metadata.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def update_metadata(date: str, doi: str, **fields) -> None:
    """Patch fields in an existing metadata.json."""
    path = _paper_dir(date, doi) / "metadata.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta.update(fields)
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def load_cached_papers(date: str, include_hidden: bool = False) -> list[dict]:
    """Return cached metadata.json records for a date, sorted by category + title.

    Hidden papers (marked excluded_from_ml) are omitted by default.
    Pass include_hidden=True to return the full set.
    """
    date_dir = PAPERS_DIR / date
    if not date_dir.exists():
        return []
    papers = []
    for meta_file in date_dir.glob("*/metadata.json"):
        try:
            p = json.loads(meta_file.read_text(encoding="utf-8"))
            if include_hidden or not p.get("hidden"):
                papers.append(p)
        except Exception:
            pass
    papers.sort(key=lambda p: (p.get("category", ""), p.get("title", "")))
    return papers


def mark_excluded(date: str, doi: str) -> None:
    """Hide a paper and mark it as excluded from ML.

    Sets hidden=True and excluded_from_ml=True in metadata.json and writes
    a .excluded marker file in the paper directory for easy filesystem filtering.
    """
    d = _paper_dir(date, doi)
    update_metadata(date, doi, hidden=True, excluded_from_ml=True)
    (d / ".excluded").touch()


# ── PDF download ──────────────────────────────────────────────────────────────

def download_pdf(doi: str, version: str, dest_dir: Path) -> Path:
    """Download the full PDF from bioRxiv and save to dest_dir/paper.pdf."""
    url = f"https://www.biorxiv.org/content/{doi}v{version}.full.pdf"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    pdf_path = dest_dir / "paper.pdf"
    with urllib.request.urlopen(req, timeout=60) as r:
        pdf_path.write_bytes(r.read())
    return pdf_path


# ── Keyword extraction ────────────────────────────────────────────────────────

def extract_keywords(title: str, abstract: str, top_n: int = 15) -> list[str]:
    """Extract meaningful unigram and bigram keywords from title + abstract.

    Title words are weighted 3× to emphasise the most specific terms.
    """
    # Title gets 3× weight
    weighted = (f"{title} " * 3) + abstract
    clean    = re.sub(r"[^a-z\-\s]", " ", weighted.lower())

    words = [w.strip("-") for w in clean.split()]
    words = [w for w in words if len(w) > 3 and w not in _STOPWORDS]
    uni   = Counter(words)

    # Bigrams from unweighted text
    raw   = re.sub(r"[^a-z\-\s]", " ", (title + " " + abstract).lower()).split()
    raw   = [w.strip("-") for w in raw]
    bi    = Counter(
        f"{raw[i]} {raw[i+1]}"
        for i in range(len(raw) - 1)
        if len(raw[i]) > 3 and len(raw[i+1]) > 3
        and raw[i] not in _STOPWORDS and raw[i+1] not in _STOPWORDS
    )

    selected: list[str] = []
    covered:  set[str]  = set()

    # Prefer bigrams with count ≥ 2
    for bigram, count in bi.most_common(8):
        if count >= 2:
            selected.append(bigram)
            w1, w2 = bigram.split()
            covered.update([w1, w2])

    # Fill remainder with top unigrams not already covered
    for word, _ in uni.most_common(40):
        if len(selected) >= top_n:
            break
        if word not in covered:
            selected.append(word)
            covered.add(word)

    return selected[:top_n]


# ── Global keywords.json ──────────────────────────────────────────────────────

def load_keywords() -> dict[str, int]:
    """Load the global keyword frequency file."""
    if not KEYWORDS_FILE.exists():
        return {}
    return json.loads(KEYWORDS_FILE.read_text(encoding="utf-8"))


def update_keywords_file(new_keywords: list[str]) -> None:
    """Increment counts for each keyword and save keywords.json."""
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    data = load_keywords()
    for kw in new_keywords:
        data[kw] = data.get(kw, 0) + 1
    # Sort descending by count
    data = dict(sorted(data.items(), key=lambda x: -x[1]))
    KEYWORDS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
