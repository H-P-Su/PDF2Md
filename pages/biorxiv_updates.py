import tempfile
import os
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from services.biorxiv import (
    ALL_CATEGORIES, load_categories, save_categories,
    fetch_papers, save_metadata, load_cached_papers, is_cached,
    has_pdf, has_markdown, download_pdf, extract_keywords,
    update_keywords_file, update_metadata, load_metadata,
    mark_excluded, doi_to_key, _paper_dir,
)
from services.converter import convert_pdf_to_markdown
from services.summarizer import generate_summary, summary_exists, load_summary

# ── Session state ─────────────────────────────────────────────────────────────
if "biorxiv_categories" not in st.session_state:
    st.session_state.biorxiv_categories = load_categories()
if "biorxiv_selected" not in st.session_state:
    st.session_state.biorxiv_selected = set()   # set of DOIs
if "biorxiv_date" not in st.session_state:
    st.session_state.biorxiv_date = date.today() - timedelta(days=1)
if "biorxiv_inited_dates" not in st.session_state:
    st.session_state.biorxiv_inited_dates = set()  # dates whose selections were pre-populated

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("bioRxiv Updates")

# ── Header row ────────────────────────────────────────────────────────────────
col_title, col_opts = st.columns([9, 1])
with col_title:
    st.title("bioRxiv Updates")
with col_opts:
    with st.popover("⚙", use_container_width=True):
        st.caption(
            f"Tracking **{len(st.session_state.biorxiv_categories)}** of "
            f"{len(ALL_CATEGORIES)} categories."
        )
        active_set = set(st.session_state.biorxiv_categories)
        new_active = []
        for cat in ALL_CATEGORIES:
            if st.checkbox(cat, value=(cat in active_set), key=f"cat_{cat}"):
                new_active.append(cat)
        st.divider()
        if st.session_state.get("biorxiv_categories_saved"):
            st.success("Categories updated.")
            st.session_state.biorxiv_categories_saved = False
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Save", type="primary", use_container_width=True):
                save_categories(new_active)
                st.session_state.biorxiv_categories = new_active
                st.session_state.biorxiv_categories_saved = True
                st.rerun()
        with c2:
            if st.button("All", use_container_width=True):
                save_categories(ALL_CATEGORIES)
                st.session_state.biorxiv_categories = list(ALL_CATEGORIES)
                st.rerun()

# ── Date picker + Fetch ───────────────────────────────────────────────────────
yesterday = date.today() - timedelta(days=1)

st.subheader("📅 Select a date")
col_date, col_fetch = st.columns([2, 1])
with col_date:
    selected_date = st.date_input(
        "Pick a date to browse",
        value=st.session_state.biorxiv_date,
        max_value=yesterday,
        format="YYYY-MM-DD",
    )
with col_fetch:
    st.write("")
    st.write("")
    fetch_clicked = st.button("Fetch papers", type="primary", use_container_width=True)

# Persist date and clear selection when it changes
if selected_date != st.session_state.biorxiv_date:
    st.session_state.biorxiv_date = selected_date
    st.session_state.biorxiv_selected = set()

date_str = selected_date.strftime("%Y-%m-%d")

# ── Fetch from API ────────────────────────────────────────────────────────────
if fetch_clicked:
    cats = st.session_state.biorxiv_categories
    if not cats:
        st.warning("No categories selected. Open ⚙ to choose some.")
    else:
        with st.spinner(f"Fetching {date_str} across {len(cats)} categories…"):
            papers = fetch_papers(date_str, cats)
        new_count = 0
        for p in papers:
            if not is_cached(date_str, p["doi"]):
                save_metadata(p, date_str)
                new_count += 1
        st.success(
            f"{len(papers)} papers found, {new_count} newly cached."
            if new_count else
            f"{len(papers)} papers found (all already cached)."
        )

# ── Load cached papers ────────────────────────────────────────────────────────
papers = load_cached_papers(date_str)          # hidden papers excluded by default

if not papers:
    st.info(f"No papers cached for {date_str}. Click **Fetch papers** to load them.")
    st.stop()

# Pre-populate selections with already-downloaded papers (once per date)
if date_str not in st.session_state.biorxiv_inited_dates:
    for p in papers:
        if p.get("pdf_path"):
            st.session_state.biorxiv_selected.add(p["doi"])
    st.session_state.biorxiv_inited_dates.add(date_str)

# Detect uncheck of a downloaded paper → mark excluded and hide
needs_rerun = False
for p in papers:
    doi = p["doi"]
    key = f"sel_{doi_to_key(doi)}"
    if (
        p.get("pdf_path")                               # has been downloaded
        and doi in st.session_state.biorxiv_selected    # was selected
        and st.session_state.get(key) is False          # user just unchecked it
    ):
        mark_excluded(date_str, doi)
        st.session_state.biorxiv_selected.discard(doi)
        needs_rerun = True
if needs_rerun:
    st.rerun()

# ── Summary bar ───────────────────────────────────────────────────────────────
all_papers_incl_hidden = load_cached_papers(date_str, include_hidden=True)
n_hidden   = len(all_papers_incl_hidden) - len(papers)

cat_counts: dict[str, int] = {}
for p in papers:
    cat_counts[p["category"]] = cat_counts.get(p["category"], 0) + 1

revised    = sum(1 for p in papers if int(p.get("version", 1)) > 1)
downloaded = sum(1 for p in papers if p.get("pdf_path"))
n_selected = len(st.session_state.biorxiv_selected)

hidden_note = f" · {n_hidden} hidden" if n_hidden else ""
st.markdown(
    f"**{len(papers)} papers** across {len(cat_counts)} categories "
    f"· {len(papers) - revised} new · {revised} revised · {downloaded} downloaded"
    f"{hidden_note}"
)
chips = "  ".join(f"`{c}` ×{n}" for c, n in sorted(cat_counts.items()))
st.caption(chips)

# ── Action bar ────────────────────────────────────────────────────────────────
st.divider()
all_dois  = {p["doi"] for p in papers}
col_sa, col_da, col_dl, col_spacer = st.columns([1.4, 1.4, 2, 5])

with col_sa:
    if st.button("Select all", use_container_width=True):
        st.session_state.biorxiv_selected = set(all_dois)
        st.rerun()
with col_da:
    if st.button("Deselect all", use_container_width=True):
        st.session_state.biorxiv_selected = set()
        st.rerun()
with col_dl:
    dl_label = f"⬇ Download selected ({n_selected})" if n_selected else "⬇ Download selected"
    dl_clicked = st.button(
        dl_label, type="primary",
        use_container_width=True,
        disabled=(n_selected == 0),
    )

# ── Download & process selected papers ───────────────────────────────────────
if dl_clicked and st.session_state.biorxiv_selected:
    selected_papers = [
        p for p in papers if p["doi"] in st.session_state.biorxiv_selected
    ]
    all_keywords: list[str] = []

    with st.status(
        f"Processing {len(selected_papers)} paper(s)…", expanded=True
    ) as status:
        for i, paper in enumerate(selected_papers, 1):
            doi     = paper["doi"]
            version = paper["version"]
            title   = paper["title"]
            d       = _paper_dir(date_str, doi)
            d.mkdir(parents=True, exist_ok=True)

            st.write(f"**{i}/{len(selected_papers)}** {title[:80]}")

            # 1. Download PDF
            pdf_path = d / "paper.pdf"
            if not pdf_path.exists():
                st.write("  ⬇ Downloading PDF…")
                pdf_path = download_pdf(doi, version, d)
            else:
                st.write("  ✓ PDF already downloaded")

            # 2. Convert to Markdown
            md_path = d / "paper.md"
            if not md_path.exists():
                st.write("  📄 Converting to Markdown…")
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_path.read_bytes())
                    tmp_path = tmp.name
                try:
                    md_content = convert_pdf_to_markdown(tmp_path)
                    md_path.write_text(md_content, encoding="utf-8")
                finally:
                    os.unlink(tmp_path)
            else:
                st.write("  ✓ Markdown already exists")
                md_content = md_path.read_text(encoding="utf-8")

            # 3. Generate summary
            md_path_str = str(md_path)
            if not summary_exists(md_path_str):
                st.write("  🧠 Generating summary…")
                generate_summary(md_content, md_path_str)
            else:
                st.write("  ✓ Summary already exists")

            # 4. Extract keywords
            st.write("  🔑 Extracting keywords…")
            kws = extract_keywords(paper["title"], paper["abstract"])
            all_keywords.extend(kws)

            # 5. Update metadata
            update_metadata(
                date_str, doi,
                pdf_path=str(pdf_path),
                md_path=str(md_path),
                keywords=kws,
            )

        # 6. Update global keywords.json
        st.write("📊 Updating keywords.json…")
        update_keywords_file(all_keywords)

        status.update(
            label=f"Done — {len(selected_papers)} paper(s) processed.",
            state="complete",
        )

    st.rerun()

st.divider()

# ── Paper list ────────────────────────────────────────────────────────────────
current_cat = None

for paper in papers:
    doi     = paper["doi"]
    version = int(paper.get("version", 1))
    is_dl   = bool(paper.get("pdf_path"))

    # Category heading
    if paper["category"] != current_cat:
        current_cat = paper["category"]
        st.subheader(current_cat.title())

    # Selection checkbox + title row
    col_chk, col_card = st.columns([0.5, 11])
    with col_chk:
        selected = st.checkbox(
            "", value=(doi in st.session_state.biorxiv_selected),
            key=f"sel_{doi_to_key(doi)}",
            label_visibility="collapsed",
        )
        if selected:
            st.session_state.biorxiv_selected.add(doi)
        else:
            st.session_state.biorxiv_selected.discard(doi)

    with col_card:
        # Badges
        badges = ""
        if version > 1:
            badges += f" `v{version}`"
        if is_dl:
            badges += " ✅"

        with st.expander(f"{'🔄 ' if version > 1 else ''}**{paper['title']}**{badges}"):
            st.markdown(f"*{paper['authors']}*")
            st.caption(
                f"{paper.get('author_corresponding_institution', '')} · "
                f"DOI: `{doi}`"
            )

            # Keywords (if extracted)
            if paper.get("keywords"):
                kw_text = " · ".join(f"`{k}`" for k in paper["keywords"])
                st.caption(f"**Keywords:** {kw_text}")

            # Tabs: Abstract | Markdown | Summary
            if is_dl:
                tab_abs, tab_md, tab_sum = st.tabs(["Abstract", "Markdown", "Summary"])
            else:
                tab_abs, = st.tabs(["Abstract"])

            with tab_abs:
                st.markdown(paper["abstract"])
                st.markdown(
                    f"[View on bioRxiv](https://www.biorxiv.org/content/{doi}v{version})"
                )

            if is_dl:
                with tab_md:
                    md_path = paper.get("md_path", "")
                    if md_path and Path(md_path).exists():
                        st.markdown(Path(md_path).read_text(encoding="utf-8"))
                    else:
                        st.info("Markdown not found.")

                with tab_sum:
                    md_path = paper.get("md_path", "")
                    if md_path and summary_exists(md_path):
                        st.markdown(load_summary(md_path))
                    else:
                        st.info("Summary not available.")
