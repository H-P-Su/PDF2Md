"""ML scoring service for bioRxiv paper recommendations.

Strategy
--------
With few or no explicit negatives, we use TF-IDF cosine similarity to the
centroid of positive examples (downloaded papers).  Once enough negative
labels accumulate (via the Ignore button), the model automatically upgrades
to a Logistic Regression classifier.

Positive  : pdf_path set and ml_label != 'negative'
Negative  : ml_label == 'negative' OR excluded_from_ml == True
Threshold : switch to classifier when negatives >= MIN_NEGATIVES_FOR_CLASSIFIER

Model artefacts are saved to storage/model/:
  vectorizer.pkl   — fitted TfidfVectorizer
  model.pkl        — centroid array (similarity mode) or LogisticRegression
  model_meta.json  — mode, training stats, timestamp
"""

import json
import pickle
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity

from services.biorxiv import PAPERS_DIR, update_metadata

MODEL_DIR = Path("storage/model")
VECTORIZER_PATH = MODEL_DIR / "vectorizer.pkl"
MODEL_PATH      = MODEL_DIR / "model.pkl"
META_PATH       = MODEL_DIR / "model_meta.json"

MIN_NEGATIVES_FOR_CLASSIFIER = 10


# ── Text feature ──────────────────────────────────────────────────────────────

def _paper_text(p: dict) -> str:
    """Weighted text: title 3× + abstract."""
    title    = p.get("title", "")
    abstract = p.get("abstract", "")
    return f"{title} {title} {title} {abstract}"


# ── Data loading ──────────────────────────────────────────────────────────────

def load_all_papers() -> list[dict]:
    """Load all metadata.json files across all dates."""
    papers = []
    for f in PAPERS_DIR.glob("*/*/metadata.json"):
        try:
            papers.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return papers


def split_labels(papers: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (positives, negatives, unlabeled)."""
    pos, neg, unlab = [], [], []
    for p in papers:
        if p.get("ml_label") == "negative" or p.get("excluded_from_ml"):
            neg.append(p)
        elif p.get("pdf_path"):
            pos.append(p)
        else:
            unlab.append(p)
    return pos, neg, unlab


# ── Training ──────────────────────────────────────────────────────────────────

def train(papers: list[dict] | None = None) -> dict:
    """Train the model and return a stats dict.

    Uses cosine-similarity mode when negatives < MIN_NEGATIVES_FOR_CLASSIFIER,
    otherwise trains a LogisticRegression classifier.
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    if papers is None:
        papers = load_all_papers()

    pos, neg, unlab = split_labels(papers)

    if not pos:
        return {"error": "No positive examples yet — download some papers first."}

    texts = [_paper_text(p) for p in papers]

    vectorizer = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
    )
    X = vectorizer.fit_transform(texts)

    if len(neg) < MIN_NEGATIVES_FOR_CLASSIFIER:
        # ── Similarity mode ───────────────────────────────────────────────
        pos_indices = [i for i, p in enumerate(papers)
                       if p.get("pdf_path") and p.get("ml_label") != "negative"]
        centroid = np.asarray(X[pos_indices].mean(axis=0))
        model_obj = centroid
        mode = "similarity"
    else:
        # ── Classifier mode ───────────────────────────────────────────────
        labeled = pos + neg
        X_labeled = vectorizer.transform([_paper_text(p) for p in labeled])
        y = [1] * len(pos) + [0] * len(neg)
        clf = LogisticRegression(max_iter=1000, class_weight="balanced")
        clf.fit(X_labeled, y)
        model_obj = clf
        mode = "classifier"

    with open(VECTORIZER_PATH, "wb") as f:
        pickle.dump(vectorizer, f)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model_obj, f)

    meta = {
        "mode":          mode,
        "n_positive":    len(pos),
        "n_negative":    len(neg),
        "n_unlabeled":   len(unlab),
        "n_total":       len(papers),
        "trained_at":    datetime.utcnow().isoformat() + "Z",
    }
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return meta


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_papers(papers: list[dict]) -> list[float]:
    """Return a score in [0, 1] for each paper. Requires a trained model."""
    with open(VECTORIZER_PATH, "rb") as f:
        vectorizer = pickle.load(f)
    with open(MODEL_PATH, "rb") as f:
        model_obj = pickle.load(f)

    texts = [_paper_text(p) for p in papers]
    X     = vectorizer.transform(texts)

    if isinstance(model_obj, np.ndarray):
        # Similarity mode — cosine similarity to centroid
        sims   = cosine_similarity(X, model_obj).flatten()
        # Normalise to [0, 1]
        lo, hi = sims.min(), sims.max()
        if hi > lo:
            scores = ((sims - lo) / (hi - lo)).tolist()
        else:
            scores = [0.5] * len(papers)
    else:
        # Classifier mode — probability of class 1
        scores = model_obj.predict_proba(X)[:, 1].tolist()

    return scores


def model_exists() -> bool:
    return VECTORIZER_PATH.exists() and MODEL_PATH.exists()


def load_model_meta() -> dict:
    if not META_PATH.exists():
        return {}
    return json.loads(META_PATH.read_text(encoding="utf-8"))


# ── Train + score all papers ──────────────────────────────────────────────────

def train_and_score_all() -> dict:
    """Train the model and write ml_score to every metadata.json."""
    papers = load_all_papers()
    stats  = train(papers)
    if "error" in stats:
        return stats

    scores = score_papers(papers)
    for paper, score in zip(papers, scores):
        doi      = paper.get("doi", "")
        date_str = paper.get("date", "")
        if doi and date_str:
            update_metadata(date_str, doi, ml_score=round(score, 4))

    stats["scored"] = len(papers)
    return stats
