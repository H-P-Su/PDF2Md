import calendar
import tempfile
import os
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from services.library import register_external_paper, get_folder_by_name, get_or_create_folder
from services.biorxiv import (
    ALL_CATEGORIES, load_categories, save_categories,
    fetch_papers, save_metadata, load_cached_papers, is_cached,
    has_pdf, has_markdown, download_pdf, extract_keywords,
    update_keywords_file, update_metadata, load_metadata,
    mark_excluded, mark_ignored, mark_ignored_clear, reset_download, doi_to_key, _paper_dir,
    get_paper_counts_for_month, get_downloaded_counts_for_month,
    get_partial_fetch_days_for_month, load_all_downloaded_papers,
)
from services.converter import convert_pdf_to_markdown
from services.tts import daily_digest_mp3
from services.summarizer import (
    generate_summary, summary_exists, load_summary, get_summary_meta,
    generate_news, news_exists, load_news, get_news_meta, clear_news,
)

# ── Query-param date selection (calendar clicks) ──────────────────────────────
_today     = date.today()
_yesterday = _today - timedelta(days=1)
if "date" in st.query_params:
    try:
        _clicked = date.fromisoformat(st.query_params["date"])
        if _clicked <= _yesterday:
            st.session_state.biorxiv_date      = _clicked
            st.session_state.biorxiv_cal_year  = _clicked.year
            st.session_state.biorxiv_cal_month = _clicked.month
            st.session_state.biorxiv_selected  = set()
    except ValueError:
        pass
    del st.query_params["date"]
    st.rerun()

# ── Session state ─────────────────────────────────────────────────────────────
if "biorxiv_categories" not in st.session_state:
    st.session_state.biorxiv_categories = load_categories()
if "biorxiv_selected" not in st.session_state:
    st.session_state.biorxiv_selected = set()
if "biorxiv_filter_downloaded" not in st.session_state:
    st.session_state.biorxiv_filter_downloaded = False
if "biorxiv_sort_by_score" not in st.session_state:
    st.session_state.biorxiv_sort_by_score = False
# Queue: doi → {doi, date_str, title, version}; persists across date navigation
if "biorxiv_download_queue" not in st.session_state:
    st.session_state.biorxiv_download_queue = {}
if "biorxiv_process_queue" not in st.session_state:
    st.session_state.biorxiv_process_queue = False
if "biorxiv_date" not in st.session_state:
    st.session_state.biorxiv_date = date.today() - timedelta(days=1)
if "biorxiv_inited_dates" not in st.session_state:
    st.session_state.biorxiv_inited_dates = set()
# Calendar view tracks which month is displayed (may differ from selected date)
if "biorxiv_cal_year" not in st.session_state:
    st.session_state.biorxiv_cal_year = st.session_state.biorxiv_date.year
if "biorxiv_cal_month" not in st.session_state:
    st.session_state.biorxiv_cal_month = st.session_state.biorxiv_date.month

today     = date.today()
yesterday = today - timedelta(days=1)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("bioRxiv Updates")

    # ── Download queue indicator ──────────────────────────────────────────────
    _queue = st.session_state.biorxiv_download_queue
    if _queue:
        st.warning(f"⬇ Download queue: **{len(_queue)} paper(s)**")
        if st.button("Process download queue", type="primary", use_container_width=True,
                     key="sb_process_queue"):
            st.session_state.biorxiv_process_queue = True
            st.rerun()
        if st.button("Clear queue", use_container_width=True, key="sb_clear_queue"):
            st.session_state.biorxiv_download_queue = {}
            st.rerun()

    st.divider()

    # ── Month navigation ──────────────────────────────────────────────────────
    cal_year  = st.session_state.biorxiv_cal_year
    cal_month = st.session_state.biorxiv_cal_month

    col_prev, col_lbl, col_next = st.columns([1, 4, 1])
    with col_prev:
        if st.button("←", key="cal_prev", use_container_width=True):
            if cal_month == 1:
                st.session_state.biorxiv_cal_year  = cal_year - 1
                st.session_state.biorxiv_cal_month = 12
            else:
                st.session_state.biorxiv_cal_month = cal_month - 1
            st.rerun()
    with col_lbl:
        st.markdown(
            f"<p style='text-align:center;margin:6px 0;font-weight:bold'>"
            f"{calendar.month_name[cal_month]} {cal_year}</p>",
            unsafe_allow_html=True,
        )
    with col_next:
        next_disabled = (cal_year == today.year and cal_month == today.month)
        if st.button("→", key="cal_next", use_container_width=True,
                     disabled=next_disabled):
            if cal_month == 12:
                st.session_state.biorxiv_cal_year  = cal_year + 1
                st.session_state.biorxiv_cal_month = 1
            else:
                st.session_state.biorxiv_cal_month = cal_month + 1
            st.rerun()

    # ── HTML calendar grid ────────────────────────────────────────────────────
    paper_counts     = get_paper_counts_for_month(cal_year, cal_month)
    downloaded_counts = get_downloaded_counts_for_month(cal_year, cal_month)
    partial_days     = get_partial_fetch_days_for_month(cal_year, cal_month)
    sel_date         = st.session_state.biorxiv_date

    cells = ""
    for week in calendar.Calendar(firstweekday=6).monthdayscalendar(cal_year, cal_month):
        cells += "<tr>"
        for day in week:
            if day == 0:
                cells += "<td></td>"
                continue
            day_date   = date(cal_year, cal_month, day)
            is_future  = day_date > today
            is_today   = day_date == today
            is_sel     = (day_date == sel_date)
            is_partial = day in partial_days
            count      = paper_counts.get(day, 0)

            num_style  = (
                "font-size:16px;font-weight:700;line-height:1;"
                "background:#ff4b4b;color:#fff;border-radius:4px;padding:1px 2px;"
                if is_sel else
                "font-size:16px;font-weight:700;line-height:1;"
                + ("color:#555;" if is_future else "")
            )
            cnt_size  = "9px" if count > 99 else "12px"
            has_dl    = downloaded_counts.get(day, 0) > 0
            cnt_color = "#4a9" if has_dl else "#aaa"
            partial_marker = (
                "<div style='font-size:9px;color:#f90;line-height:1;margin-top:0px'>*partial</div>"
                if is_partial or is_today else ""
            )
            cnt_html  = (
                f"<div style='font-size:{cnt_size};color:{cnt_color};line-height:1.1;margin-top:1px'>"
                f"{count if count > 0 else '&nbsp;'}</div>"
                f"{partial_marker}"
            )
            if is_future:
                day_html = f"<div style='{num_style}'>{day}</div>"
            else:
                day_html = (
                    f"<a href='?date={day_date.isoformat()}' target='_self' "
                    f"style='text-decoration:none;display:inline-block'>"
                    f"<div style='{num_style}'>{day}</div></a>"
                )
            cells += (
                f"<td style='text-align:center;padding:1px 0;vertical-align:top'>"
                f"{day_html}{cnt_html}</td>"
            )
        cells += "</tr>"

    st.markdown(f"""
    <table style='width:100%;border-collapse:collapse;table-layout:fixed'>
      <tr>{''.join(f"<th style='font-size:11px;color:#888;text-align:center;padding:1px 0'>{n}</th>"
                   for n in ["Su","Mo","Tu","We","Th","Fr","Sa"])}</tr>
      {cells}
    </table>
    """, unsafe_allow_html=True)

    # ── Day-select buttons (below calendar) ───────────────────────────────────
    st.caption("Navigate:")
    c1, c2, c3 = st.columns([1, 3, 1])
    with c1:
        if st.button("◀", key="day_prev", use_container_width=True):
            prev_day = sel_date - timedelta(days=1)
            st.session_state.biorxiv_date     = prev_day
            st.session_state.biorxiv_cal_year  = prev_day.year
            st.session_state.biorxiv_cal_month = prev_day.month
            st.session_state.biorxiv_selected  = set()
            st.rerun()
    with c2:
        st.markdown(
            f"<p style='text-align:center;font-size:0.78em;margin:6px 0'>"
            f"{sel_date.strftime('%b %-d')}</p>",
            unsafe_allow_html=True,
        )
    with c3:
        if st.button("▶", key="day_next", use_container_width=True,
                     disabled=(sel_date >= today)):
            next_day = sel_date + timedelta(days=1)
            st.session_state.biorxiv_date     = next_day
            st.session_state.biorxiv_cal_year  = next_day.year
            st.session_state.biorxiv_cal_month = next_day.month
            st.session_state.biorxiv_selected  = set()
            st.rerun()

    st.divider()

# ── Main panel ────────────────────────────────────────────────────────────────
selected_date = st.session_state.biorxiv_date
date_str      = selected_date.strftime("%Y-%m-%d")

col_title, col_opts = st.columns([9, 1])
with col_title:
    st.title("bioRxiv Updates")
with col_opts:
    with st.popover("⚙️"):
        # ── ML model ──────────────────────────────────────────────────────
        st.markdown("**ML scoring**")
        from services.ml import train_and_score_all, load_model_meta, model_exists, score_papers_for_date as _spfd
        if model_exists():
            mm = load_model_meta()
            st.caption(
                f"v{mm.get('model_version','?')} · {mm.get('mode','?')} · "
                f"{mm.get('n_positive',0)}+ / {mm.get('n_negative',0)}− · "
                f"Trained {mm.get('trained_at','')[:10]}"
            )
        else:
            st.caption("No model trained yet.")
        if st.button("🤖 Retrain model", use_container_width=True, key="opt_retrain"):
            with st.spinner("Training…"):
                from services.ml import train, load_all_papers
                stats = train(load_all_papers())
            if "error" in stats:
                st.error(stats["error"])
            else:
                st.success(
                    f"Retrained — v{stats.get('model_version','?')} · "
                    f"{stats['mode']} mode · "
                    f"{stats['n_positive']}+ / {stats['n_negative']}−"
                )
        if model_exists():
            if st.button("📊 Score stale papers", use_container_width=True, key="opt_score_all"):
                from services.ml import score_all_stale
                with st.spinner("Scoring…"):
                    scored = score_all_stale()
                st.success(f"Scored {scored} stale paper(s).")

        st.divider()

        # ── Sync ──────────────────────────────────────────────────────────
        st.markdown("**Sync to PDF Library**")
        st.caption("Register all downloaded bioRxiv papers in the PDF Library database.")
        if st.button("🔄 Sync to PDF Library", use_container_width=True, key="opt_sync"):
            from services.library import paper_exists as _paper_exists
            all_downloaded = load_all_downloaded_papers()
            folder_id = get_or_create_folder("BioRxiv")
            new_count = already_count = 0
            for p in all_downloaded:
                if _paper_exists(p["doi"]):
                    already_count += 1
                else:
                    register_external_paper(
                        title=p["title"],
                        filename=p["doi"],
                        pdf_path=p["pdf_path"],
                        md_path=p["md_path"],
                        folder_id=folder_id,
                    )
                    new_count += 1
            st.success(f'{new_count} added, {already_count} already registered in "BioRxiv" folder.')

        st.divider()

        # ── Clear PDFs ────────────────────────────────────────────────────
        st.markdown("**Clear PDF files**")
        st.caption("Remove PDFs where Markdown already exists to free disk space.")
        all_dl = load_all_downloaded_papers()
        clearable = [
            p for p in all_dl
            if p.get("pdf_path") and Path(p["pdf_path"]).exists()
            and p.get("md_path") and Path(p["md_path"]).exists()
        ]
        if clearable:
            total_mb = sum(Path(p["pdf_path"]).stat().st_size for p in clearable) / 1_048_576
            st.caption(f"{len(clearable)} PDF(s) · {total_mb:.1f} MB freeable")
            if st.button(f"🗑 Delete {len(clearable)} PDF(s)", use_container_width=True,
                         key="opt_clear_pdfs"):
                cleared = 0
                for p in clearable:
                    try:
                        Path(p["pdf_path"]).unlink()
                        # Date is the parent-of-parent directory name
                        date_part = Path(p["pdf_path"]).parent.parent.name
                        update_metadata(date_part, p["doi"], pdf_path="")
                        cleared += 1
                    except Exception:
                        pass
                st.success(f"Deleted {cleared} PDF(s).")
        else:
            st.caption("No PDFs to clear (none have Markdown yet, or already cleared).")

        st.divider()

        # ── Categories ────────────────────────────────────────────────────
        st.markdown("**Categories**")
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
            if st.button("Save", type="primary", use_container_width=True, key="opt_save_cats"):
                save_categories(new_active)
                st.session_state.biorxiv_categories = new_active
                st.session_state.biorxiv_categories_saved = True
                st.rerun()
        with c2:
            if st.button("All", use_container_width=True, key="opt_all_cats"):
                save_categories(ALL_CATEGORIES)
                st.session_state.biorxiv_categories = list(ALL_CATEGORIES)
                st.rerun()

st.subheader(selected_date.strftime("%A, %B %-d %Y"))

col_fetch, col_digest, col_spacer = st.columns([2, 2, 3])
with col_fetch:
    fetch_clicked = st.button("Fetch papers for this date", type="primary",
                               use_container_width=True)
with col_digest:
    digest_clicked = st.button("🎧 Audio digest", use_container_width=True)

# ── Fetch from API ────────────────────────────────────────────────────────────
if fetch_clicked:
    cats = st.session_state.biorxiv_categories
    if not cats:
        st.warning("No categories selected. Open ⚙ Options in the sidebar.")
    else:
        with st.spinner(f"Fetching {date_str} across {len(cats)} categories…"):
            papers_raw = fetch_papers(date_str, cats)
        new_count = 0
        for p in papers_raw:
            if not is_cached(date_str, p["doi"]):
                save_metadata(p, date_str)
                new_count += 1
        # Refresh counts in sidebar calendar
        st.session_state.biorxiv_cal_year  = selected_date.year
        st.session_state.biorxiv_cal_month = selected_date.month
        st.success(
            f"{len(papers_raw)} papers found, {new_count} newly cached."
            if new_count else
            f"{len(papers_raw)} papers found (all already cached)."
        )

# ── Load cached papers ────────────────────────────────────────────────────────
papers = load_cached_papers(date_str)

if not papers:
    st.info(f"No papers cached for {date_str}. Click **Fetch papers for this date**.")
    st.stop()

# ── Audio digest ──────────────────────────────────────────────────────────────
digest_cache = Path("storage/Biorxiv_papers") / date_str / "digest.mp3"
if digest_clicked:
    with st.spinner("Generating audio digest… this may take a minute."):
        mp3 = daily_digest_mp3(date_str, papers)
    st.audio(mp3, format="audio/mp3")
elif digest_cache.exists():
    st.audio(digest_cache.read_bytes(), format="audio/mp3")

# ── Auto-score stale papers for this date ─────────────────────────────────────
from services.ml import score_papers_for_date, model_exists as _model_exists
if _model_exists():
    score_papers_for_date(date_str)
    papers = load_cached_papers(date_str)  # reload with fresh scores

# Pre-populate selections with already-downloaded papers (once per date)
if date_str not in st.session_state.biorxiv_inited_dates:
    for p in papers:
        if p.get("pdf_path"):
            st.session_state.biorxiv_selected.add(p["doi"])
    st.session_state.biorxiv_inited_dates.add(date_str)

# Sync biorxiv_selected from checkbox widget states (so action bar counts are current)
for p in papers:
    doi = p["doi"]
    key = f"sel_{doi_to_key(doi)}"
    if key in st.session_state:
        if st.session_state[key]:
            st.session_state.biorxiv_selected.add(doi)
        else:
            st.session_state.biorxiv_selected.discard(doi)

# Detect uncheck of a downloaded paper → mark excluded and hide
needs_rerun = False
for p in papers:
    doi = p["doi"]
    key = f"sel_{doi_to_key(doi)}"
    if (
        p.get("pdf_path")
        and doi in st.session_state.biorxiv_selected
        and st.session_state.get(key) is False
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

# ── App-level queue banner ────────────────────────────────────────────────────
_q = st.session_state.biorxiv_download_queue
if _q:
    st.warning(
        f"⬇ **{len(_q)} paper(s) in download queue** across "
        f"{len({v['date_str'] for v in _q.values()})} date(s). "
        f"Use **Process download queue** in the sidebar to download."
    )

# ── Action bar ────────────────────────────────────────────────────────────────
st.divider()
all_dois = {p["doi"] for p in papers}
col_sa, col_da, col_dl, col_q, col_filt, col_sort = st.columns([1.3, 1.3, 2.4, 1.6, 1.6, 1.6])

with col_sa:
    if st.button("Select all", use_container_width=True):
        st.session_state.biorxiv_selected = set(all_dois)
        st.rerun()
with col_da:
    if st.button("Deselect all", use_container_width=True):
        st.session_state.biorxiv_selected = set()
        st.rerun()
with col_q:
    n_queueable = sum(
        1 for doi in st.session_state.biorxiv_selected
        if doi not in st.session_state.biorxiv_download_queue
        and not next((p for p in papers if p["doi"] == doi and p.get("pdf_path")), None)
    )
    q_label = f"🔖 Queue ({n_queueable})" if n_queueable else "🔖 Queue"
    if st.button(q_label, use_container_width=True, disabled=(n_queueable == 0)):
        for p in papers:
            if (p["doi"] in st.session_state.biorxiv_selected
                    and not p.get("pdf_path")
                    and p["doi"] not in st.session_state.biorxiv_download_queue):
                st.session_state.biorxiv_download_queue[p["doi"]] = {
                    "doi":      p["doi"],
                    "date_str": date_str,
                    "title":    p["title"],
                    "version":  p["version"],
                }
        st.rerun()
with col_filt:
    filt_active = st.session_state.biorxiv_filter_downloaded
    filt_label  = "All papers" if filt_active else "Downloaded"
    if st.button(filt_label, use_container_width=True,
                 type="primary" if filt_active else "secondary"):
        st.session_state.biorxiv_filter_downloaded = not filt_active
        st.rerun()
with col_sort:
    sort_by_score = st.session_state.biorxiv_sort_by_score
    sort_label    = "⭐ By score" if sort_by_score else "Sort by score"
    if st.button(sort_label, use_container_width=True,
                 type="primary" if sort_by_score else "secondary"):
        st.session_state.biorxiv_sort_by_score = not sort_by_score
        st.rerun()
with col_dl:
    selected_papers_preview = [p for p in papers if p["doi"] in st.session_state.biorxiv_selected]
    n_already_dl = sum(1 for p in selected_papers_preview if p.get("pdf_path"))
    n_to_dl = n_selected - n_already_dl
    dl_label = f"⬇ Download ({n_already_dl}/{n_selected})" if n_selected else "⬇ Download"
    dl_clicked = st.button(
        dl_label, type="primary",
        use_container_width=True,
        disabled=(n_selected == 0),
    )

# ── Ollama availability check ─────────────────────────────────────────────────
def _ollama_running() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


# ── Shared download processor ─────────────────────────────────────────────────
def _run_download_phases(paper_list: list[dict], date_str_map: dict[str, str]) -> None:
    """Download, convert, keyword-extract, and summarise a list of papers.

    paper_list    — list of metadata dicts (must include doi, title, version, abstract)
    date_str_map  — {doi: date_str} so papers from multiple dates are handled correctly
    """
    total = len(paper_list)
    ollama_ok = _ollama_running()

    # Phase 1 — Download PDFs
    st.write("**Phase 1: Downloading PDFs**")
    pdf_paths: dict[str, Path] = {}
    for i, paper in enumerate(paper_list, 1):
        doi      = paper["doi"]
        ds       = date_str_map[doi]
        d        = _paper_dir(ds, doi)
        d.mkdir(parents=True, exist_ok=True)
        pdf_path = d / "paper.pdf"
        if not pdf_path.exists():
            st.write(f"  ⬇ {i}/{total} {paper['title'][:70]}")
            pdf_path = download_pdf(doi, paper["version"], d)
        else:
            st.write(f"  ✓ {i}/{total} already downloaded")
        pdf_paths[doi] = pdf_path

    # Phase 2 — Convert to Markdown
    st.write("**Phase 2: Converting to Markdown**")
    md_paths: dict[str, Path] = {}
    for i, paper in enumerate(paper_list, 1):
        doi      = paper["doi"]
        pdf_path = pdf_paths[doi]
        md_path  = pdf_path.parent / "paper.md"
        if not md_path.exists():
            st.write(f"  📄 {i}/{total} {paper['title'][:70]}")
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_path.read_bytes())
                tmp_path = tmp.name
            try:
                md_content = convert_pdf_to_markdown(tmp_path)
                md_path.write_text(md_content, encoding="utf-8")
            finally:
                os.unlink(tmp_path)
        else:
            st.write(f"  ✓ {i}/{total} already converted")
        md_paths[doi] = md_path

    # Phase 3 — Keywords + metadata + library registration
    st.write("**Phase 3: Extracting keywords**")
    all_keywords: list[str] = []
    folder_id = get_or_create_folder("BioRxiv")
    for paper in paper_list:
        doi = paper["doi"]
        ds  = date_str_map[doi]
        kws = extract_keywords(paper["title"], paper["abstract"])
        all_keywords.extend(kws)
        update_metadata(ds, doi,
                        pdf_path=str(pdf_paths[doi]),
                        md_path=str(md_paths[doi]),
                        keywords=kws)
        register_external_paper(
            title=paper["title"],
            filename=doi,
            pdf_path=str(pdf_paths[doi]),
            md_path=str(md_paths[doi]),
            folder_id=folder_id,
        )
    update_keywords_file(all_keywords)
    st.write(f'  ✓ {len(all_keywords)} keywords · {total} paper(s) registered in "BioRxiv" folder')

    # Phase 4 — Summarisation
    if not ollama_ok:
        st.warning("Ollama is not running — summaries skipped. "
                   "Start Ollama and use **Summarize downloaded** to generate them later.")
    else:
        st.write("**Phase 4: Generating summaries**")
        for i, paper in enumerate(paper_list, 1):
            doi         = paper["doi"]
            md_path_str = str(md_paths[doi])
            if not summary_exists(md_path_str):
                st.write(f"  🧠 {i}/{total} {paper['title'][:70]}")
                generate_summary(md_paths[doi].read_text(encoding="utf-8"), md_path_str)
            else:
                st.write(f"  ✓ {i}/{total} summary already exists")


# ── Process download queue (triggered from sidebar) ───────────────────────────
if st.session_state.biorxiv_process_queue and st.session_state.biorxiv_download_queue:
    queue = st.session_state.biorxiv_download_queue
    # Load full metadata for each queued paper
    queued_papers = []
    date_str_map: dict[str, str] = {}
    for doi, entry in queue.items():
        meta = load_metadata(entry["date_str"], doi)
        if meta:
            queued_papers.append(meta)
            date_str_map[doi] = entry["date_str"]
    if queued_papers:
        with st.status(f"Processing download queue ({len(queued_papers)} papers)…",
                       expanded=True) as status:
            _run_download_phases(queued_papers, date_str_map)
            status.update(label=f"Queue complete — {len(queued_papers)} paper(s) processed.",
                          state="complete")
    st.session_state.biorxiv_download_queue = {}
    st.session_state.biorxiv_process_queue  = False
    st.rerun()


# ── Download & process selected papers (current date) ────────────────────────
if dl_clicked and st.session_state.biorxiv_selected:
    selected_papers = [p for p in papers if p["doi"] in st.session_state.biorxiv_selected]
    ds_map = {p["doi"]: date_str for p in selected_papers}
    with st.status(f"Processing {len(selected_papers)} paper(s)…", expanded=True) as status:
        _run_download_phases(selected_papers, ds_map)
        status.update(label=f"Done — {len(selected_papers)} paper(s) processed.",
                      state="complete")
    # Remove downloaded papers from queue
    for p in selected_papers:
        st.session_state.biorxiv_download_queue.pop(p["doi"], None)
    st.rerun()

# ── Summarize downloaded papers ───────────────────────────────────────────────
papers_needing_generation = [
    p for p in papers
    if p.get("md_path") and (
        not summary_exists(p["md_path"]) or not news_exists(p["md_path"])
    )
]
if papers_needing_generation:
    col_sum, col_sum_spacer = st.columns([3, 7])
    with col_sum:
        sum_clicked = st.button(
            f"🧠 Generate summaries/news ({len(papers_needing_generation)})",
            use_container_width=True,
            disabled=not _ollama_running(),
            help="Ollama must be running. Start with: ollama serve" if not _ollama_running() else "",
        )
    if sum_clicked:
        with st.status(f"Generating for {len(papers_needing_generation)} paper(s)…",
                       expanded=True) as status:
            for i, paper in enumerate(papers_needing_generation, 1):
                md_path_str = paper["md_path"]
                md_content  = Path(md_path_str).read_text(encoding="utf-8")
                st.write(f"  🧠 {i}/{len(papers_needing_generation)} {paper['title'][:70]}")
                if not summary_exists(md_path_str):
                    generate_summary(md_content, md_path_str)
                if not news_exists(md_path_str):
                    generate_news(md_content, md_path_str)
            status.update(label="Generation complete.", state="complete")
        st.rerun()

st.divider()

# ── Paper list ────────────────────────────────────────────────────────────────
visible_papers = (
    [p for p in papers if p.get("pdf_path")]
    if st.session_state.biorxiv_filter_downloaded
    else papers
)
if st.session_state.biorxiv_filter_downloaded and not visible_papers:
    st.info("No downloaded papers for this date.")
    st.stop()

if st.session_state.biorxiv_sort_by_score:
    visible_papers = sorted(
        visible_papers,
        key=lambda p: p.get("ml_score", -1),
        reverse=True,
    )

current_cat = None

for paper in visible_papers:
    doi     = paper["doi"]
    version = int(paper.get("version", 1))
    is_dl   = bool(paper.get("pdf_path"))

    if paper["category"] != current_cat:
        current_cat = paper["category"]
        st.subheader(current_cat.title())

    col_chk, col_card = st.columns([0.5, 11])
    with col_chk:
        selected = st.checkbox(
            "Select paper", value=(doi in st.session_state.biorxiv_selected),
            key=f"sel_{doi_to_key(doi)}",
            label_visibility="collapsed",
        )
        if selected:
            st.session_state.biorxiv_selected.add(doi)
        else:
            st.session_state.biorxiv_selected.discard(doi)

    with col_card:
        badges = ""
        if version > 1:
            badges += f" `v{version}`"
        if is_dl:
            badges += " ✅"
        if paper.get("ml_label") == "negative":
            badges += " 🚫"
        ml_score = paper.get("ml_score")
        score_str = f" ({ml_score:.2f})" if ml_score is not None else ""

        with st.expander(f"{'🔄 ' if version > 1 else ''}**{paper['title']}**{score_str}{badges}"):
            st.markdown(f"*{paper['authors']}*")
            st.caption(
                f"{paper.get('author_corresponding_institution', '')} · "
                f"DOI: `{doi}`"
            )

            if paper.get("keywords"):
                kw_text = " · ".join(f"`{k}`" for k in paper["keywords"])
                st.caption(f"**Keywords:** {kw_text}")

            if is_dl:
                tab_abs, tab_md, tab_sum, tab_news = st.tabs(["Abstract", "Markdown", "Summary", "News Article"])
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
                    md_path   = paper.get("md_path", "")
                    ollama_ok = _ollama_running()
                    if md_path and summary_exists(md_path):
                        meta = get_summary_meta(md_path)
                        if meta:
                            st.caption(
                                f"Summarizer v{meta.get('version', '?')} · "
                                f"Generated {meta.get('generated_at', '')[:10]}"
                            )
                        st.markdown(load_summary(md_path))
                        if st.button("↺ Regenerate summary",
                                     key=f"regen_sum_{doi_to_key(doi)}",
                                     disabled=not ollama_ok,
                                     help="Ollama must be running" if not ollama_ok else ""):
                            with st.spinner("Regenerating…"):
                                from services.summarizer import clear_summary
                                clear_summary(md_path)
                                generate_summary(Path(md_path).read_text(encoding="utf-8"), md_path)
                            st.rerun()
                    else:
                        st.info("No summary yet.")
                        if st.button("Generate Summary",
                                     key=f"gen_sum_{doi_to_key(doi)}",
                                     type="primary",
                                     disabled=not ollama_ok,
                                     help="Ollama must be running" if not ollama_ok else ""):
                            with st.spinner("Generating…"):
                                generate_summary(Path(md_path).read_text(encoding="utf-8"), md_path)
                            st.rerun()

                with tab_news:
                    md_path  = paper.get("md_path", "")
                    ollama_ok = _ollama_running()
                    if md_path and news_exists(md_path):
                        meta = get_news_meta(md_path)
                        if meta:
                            st.caption(
                                f"Summarizer v{meta.get('version', '?')} · "
                                f"Generated {meta.get('generated_at', '')[:10]}"
                            )
                        st.markdown(load_news(md_path))
                        if st.button("↺ Regenerate news article",
                                     key=f"regen_news_{doi_to_key(doi)}",
                                     disabled=not ollama_ok,
                                     help="Ollama must be running" if not ollama_ok else ""):
                            with st.spinner("Regenerating…"):
                                clear_news(md_path)
                                generate_news(Path(md_path).read_text(encoding="utf-8"), md_path)
                            st.rerun()
                    else:
                        st.info("News article not available.")
                        if st.button("Generate News Article",
                                     key=f"gen_news_{doi_to_key(doi)}",
                                     type="primary",
                                     disabled=not ollama_ok,
                                     help="Ollama must be running" if not ollama_ok else ""):
                            with st.spinner("Generating…"):
                                generate_news(Path(md_path).read_text(encoding="utf-8"), md_path)
                            st.rerun()

                # ── ML label ──────────────────────────────────────────────
                is_ignored = paper.get("ml_label") == "negative"
                ig_label   = "🚫 Ignored (negative example)" if is_ignored else "🚫 Ignore for ML"
                ig_help    = "Remove negative label" if is_ignored else "Mark as negative training example"
                if st.button(ig_label, key=f"ignore_{doi_to_key(doi)}",
                             use_container_width=True, help=ig_help):
                    if is_ignored:
                        mark_ignored_clear(date_str, doi)
                    else:
                        mark_ignored(date_str, doi)
                    st.rerun()

                # ── Reset download (incomplete only) ───────────────────────
                pdf_missing = paper.get("pdf_path") and not Path(paper["pdf_path"]).exists()
                md_missing  = not paper.get("md_path") or not Path(paper["md_path"]).exists()
                is_incomplete = pdf_missing or md_missing
                if is_incomplete:
                    st.divider()
                    missing_parts = []
                    if pdf_missing:
                        missing_parts.append("PDF")
                    if md_missing:
                        missing_parts.append("Markdown")
                    st.warning(f"⚠ Incomplete download — missing: {', '.join(missing_parts)}")
                    if st.button("↺ Reset & re-download", key=f"reset_{doi_to_key(doi)}",
                                 type="primary",
                                 help="Clear partial files so this paper can be re-downloaded"):
                        reset_download(date_str, doi)
                        st.session_state.biorxiv_selected.discard(doi)
                        st.rerun()
