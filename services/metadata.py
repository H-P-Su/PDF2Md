"""
Extract DOI, PMID, and author list from converted paper Markdown.
All extraction is heuristic — results are best-effort.
"""

import re

_DOI_URL_RE = re.compile(
    r'https?://(?:dx\.)?doi\.org/(10\.\d{4,}/\S+)', re.IGNORECASE
)
_DOI_RE = re.compile(
    r'\bDOI[:\s]*(10\.\d{4,}/\S+)', re.IGNORECASE
)
_PMID_RE = re.compile(
    r'\bPMID[:\s]*(\d{6,9})\b', re.IGNORECASE
)

_AFFILIATION_RE = re.compile(
    r'university|department|institute|hospital|college|school|'
    r'laboratory|\blab\b|center|centre|faculty|division|foundation',
    re.IGNORECASE,
)


def extract_metadata(md_text: str) -> dict:
    """Return dict with keys: doi, pmid, authors (each may be None)."""
    lines = md_text.splitlines()

    doi = None
    pmid = None
    authors = None

    # Scan full text for DOI and PMID
    for line in lines:
        if doi is None:
            m = _DOI_URL_RE.search(line)
            if m:
                doi = m.group(1).rstrip('.,;)')
            else:
                m = _DOI_RE.search(line)
                if m:
                    doi = m.group(1).rstrip('.,;)')

        if pmid is None:
            m = _PMID_RE.search(line)
            if m:
                pmid = m.group(1)

        if doi and pmid:
            break

    # Scan first 40 lines for an author line (skip line 0 — usually the title heading)
    for line in lines[1:40]:
        s = line.strip().lstrip('#').strip()

        if not s or len(s) < 5:
            continue
        # Skip affiliation lines
        if _AFFILIATION_RE.search(s):
            continue
        # Skip lines with URLs, emails, or DOIs
        if re.search(r'https?://|@|\bdoi\b', s, re.IGNORECASE):
            continue
        # Skip lines that are mostly numbers or symbols (equations, citations)
        if len(re.findall(r'[a-zA-Z]', s)) / max(len(s), 1) < 0.5:
            continue

        # Author lines contain 2+ "Firstname Lastname" patterns
        name_matches = re.findall(r'\b[A-Z][a-z]+(?:[\s\-][A-Z][a-z]+)+', s)
        if len(name_matches) >= 2:
            # Strip trailing superscript markers and tidy whitespace
            clean = re.sub(r'[†‡§¶∗*\d]+', ' ', s)
            clean = re.sub(r'\s+', ' ', clean).strip().strip(',')
            if clean:
                authors = clean
                break

    return {"doi": doi, "pmid": pmid, "authors": authors}
