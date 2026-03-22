import os
import tempfile
from pathlib import Path

import streamlit as st

from services.converter import convert_pdf_to_markdown
from services.tts import markdown_to_mp3
from services.metadata import extract_metadata
from services.summarizer import (
    summary_exists, news_exists,
    load_summary, load_news,
    get_summary_meta, get_news_meta,
    clear_summary, clear_news,
    generate_summary, generate_news,
)
from services.library import (
    save_paper, get_paper, get_papers_in_folder, get_all_papers, paper_exists,
    rename_paper, move_paper, delete_paper,
    search_papers_by_title, search_papers_by_content,
    get_all_folders, create_folder, delete_folder,
    get_comments, add_comment, update_comment, delete_comment,
    get_all_tags, create_tag, delete_tag, get_paper_tags,
    add_paper_tag, remove_paper_tag,
    register_external_paper, get_folder_by_name, get_or_create_folder,
    TAG_COLORS,
)
from services.biorxiv import load_all_downloaded_papers

# ── Session state ─────────────────────────────────────────────────────────────
_defaults = {
    "selected_paper_id":    None,
    "show_new_folder":      False,
    "pending_delete_paper": None,
    "pending_delete_folder": None,
    "editing_title":        False,
    "editing_comment_id":   None,
    "show_tag_manager":     False,
    "content_search_results": None,
    "mp3_cache": {},          # paper_id -> mp3 bytes or "processing"
    "generating_summary": False,
    "generating_news":    False,
    "lib_search_query":   "",
    "lib_search_mode":    "Title",  # "Title" | "Full text"
    "lib_folder_filter":  None,   # None = all folders
    "lib_sort":           "date", # "date" | "title" | "folder"
}
for key, val in _defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_title(stem: str) -> str:
    """Strip leading author/year prefixes from filename stems.

    Handles patterns like:
      surname-et-al-2026-actual-title  →  Actual Title
      surname-2026-actual-title        →  Actual Title
    Falls back to the original stem (spaces for dashes) if no match.
    """
    import re
    cleaned = re.sub(
        r'^[a-z]+(?:-et-al)?-\d{4}-',
        '',
        stem,
        flags=re.IGNORECASE,
    )
    return cleaned.replace('-', ' ').title()


def _tag_badges(tags, *, size: str = "0.78em") -> str:
    parts = [
        f'<span style="background:{t["color"]};color:#fff;'
        f'padding:2px 9px;border-radius:10px;font-size:{size};'
        f'margin-right:4px;white-space:nowrap">{t["name"]}</span>'
        for t in tags
    ]
    return "".join(parts)


def _select_paper(paper_id: int):
    st.session_state.selected_paper_id = paper_id
    st.session_state.editing_title = False
    st.session_state.editing_comment_id = None
    st.session_state.content_search_results = None
    st.session_state.generating_summary = False
    st.session_state.generating_news = False


# Handle clickable title and trash links via query params
if "open_paper" in st.query_params:
    try:
        _select_paper(int(st.query_params["open_paper"]))
    except (ValueError, KeyError):
        pass
    del st.query_params["open_paper"]
    st.rerun()

if "del_paper" in st.query_params:
    try:
        st.session_state.pending_delete_paper = int(st.query_params["del_paper"])
    except (ValueError, KeyError):
        pass
    del st.query_params["del_paper"]
    st.rerun()


# ── Sidebar — upload only ──────────────────────────────────────────────────────
with st.sidebar:
    st.header("PDF Library")
    st.subheader("Upload")

    folders = get_all_folders()
    folder_map = {f["id"]: f["name"] for f in folders}
    folder_opts = [None] + [f["id"] for f in folders]

    upload_folder = st.selectbox(
        "Add to folder",
        options=folder_opts,
        format_func=lambda x: "Root" if x is None else folder_map[x],
        key="upload_folder_select",
    )

    uploaded_file = st.file_uploader("Choose a PDF", type=["pdf"], label_visibility="collapsed")

    if uploaded_file:
        if paper_exists(uploaded_file.name):
            st.warning(f"**{uploaded_file.name}** is already in the library.")
        else:
            if st.button("Convert & Add to Library", type="primary", use_container_width=True):
                pdf_bytes = uploaded_file.read()
                title = _clean_title(Path(uploaded_file.name).stem)
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_bytes)
                    tmp_path = tmp.name
                try:
                    with st.spinner(f'Converting "{title}" …'):
                        md_content = convert_pdf_to_markdown(tmp_path)
                    paper_id = save_paper(title, uploaded_file.name, pdf_bytes, md_content, upload_folder)
                    _select_paper(paper_id)
                    st.success("Added to library.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Conversion failed: {exc}")
                finally:
                    os.unlink(tmp_path)


# ── Main panel ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Compact caption cells (folder, date) */
div[data-testid='stCaptionContainer'] {
    padding-top: 0.1rem !important;
    padding-bottom: 0.1rem !important;
    line-height: 1.2 !important;
}
/* Trash icon — no box, just the emoji */
.trash-btn button {
    background: none !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    min-height: unset !important;
    color: inherit !important;
}
.trash-btn button:hover {
    background: none !important;
    opacity: 0.7;
}
</style>
""", unsafe_allow_html=True)
_col_hdr, _col_gear = st.columns([11, 1])
with _col_gear:
    with st.popover("⚙️"):
        st.markdown("**Sync from bioRxiv Updates**")
        st.caption("Register all downloaded bioRxiv papers in the PDF Library database.")
        if st.button("🔄 Sync from bioRxiv", use_container_width=True, key="lib_sync"):
            all_downloaded = load_all_downloaded_papers()
            folder_id = get_or_create_folder("BioRxiv")
            new_count = already_count = 0
            for p in all_downloaded:
                if paper_exists(p["doi"]):
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
        st.markdown("**Folders**")
        _pop_folders = get_all_folders()
        for _f in _pop_folders:
            _cnt = len(get_papers_in_folder(_f["id"]))
            fc1, fc2 = st.columns([3, 1])
            with fc1:
                st.markdown(
                    f'📁 **{_f["name"]}** <span style="color:#888">({_cnt})</span>',
                    unsafe_allow_html=True,
                )
            with fc2:
                if st.button("🗑", key=f"pop_delf_{_f['id']}", help=f'Delete "{_f["name"]}"'):
                    st.session_state.pending_delete_folder = _f["id"]
                    st.rerun()
        if not _pop_folders:
            st.caption("No folders yet.")

        st.divider()
        st.markdown("**New folder**")
        with st.form("new_folder_form", clear_on_submit=True):
            nf_name = st.text_input("Folder name", label_visibility="collapsed",
                                    placeholder="Folder name…")
            if st.form_submit_button("Create folder", use_container_width=True):
                if nf_name.strip():
                    create_folder(nf_name.strip())
                    st.rerun()

if st.session_state.selected_paper_id is None:
    # ── Library header row ────────────────────────────────────────────────────
    all_folders = get_all_folders()
    folder_map  = {f["id"]: f["name"] for f in all_folders}

    hc1, hc1b, hc2, hc3 = st.columns([4, 1, 2, 2])
    with hc1:
        search_q = st.text_input(
            "Search",
            value=st.session_state.lib_search_query,
            placeholder="Search…",
            label_visibility="collapsed",
            key="lib_search_input",
        )
        if search_q != st.session_state.lib_search_query:
            st.session_state.lib_search_query = search_q
            st.rerun()
    with hc1b:
        search_mode = st.radio(
            "Search mode",
            options=["Title", "Full text"],
            index=0 if st.session_state.lib_search_mode == "Title" else 1,
            label_visibility="collapsed",
            key="lib_search_mode_radio",
        )
        if search_mode != st.session_state.lib_search_mode:
            st.session_state.lib_search_mode = search_mode
            st.rerun()
    with hc2:
        folder_opts = [None] + [f["id"] for f in all_folders]
        cur_filter  = st.session_state.lib_folder_filter
        cur_idx     = folder_opts.index(cur_filter) if cur_filter in folder_opts else 0
        chosen_folder = st.selectbox(
            "Folder filter",
            options=folder_opts,
            index=cur_idx,
            format_func=lambda x: "All folders" if x is None else folder_map.get(x, "?"),
            label_visibility="collapsed",
            key="lib_folder_filter_sel",
        )
        if chosen_folder != st.session_state.lib_folder_filter:
            st.session_state.lib_folder_filter = chosen_folder
            st.rerun()
    with hc3:
        sort_labels = {"date": "Sort: Date", "title": "Sort: Title", "folder": "Sort: Folder"}
        cur_sort = st.session_state.lib_sort
        new_sort = st.selectbox(
            "Sort",
            options=list(sort_labels.keys()),
            index=list(sort_labels.keys()).index(cur_sort),
            format_func=lambda x: sort_labels[x],
            label_visibility="collapsed",
            key="lib_sort_sel",
        )
        if new_sort != cur_sort:
            st.session_state.lib_sort = new_sort
            st.rerun()

    st.divider()

    # ── Collect and filter papers ─────────────────────────────────────────────
    q = st.session_state.lib_search_query.strip()

    if q and st.session_state.lib_search_mode == "Full text":
        raw_papers = search_papers_by_content(q)
        if st.session_state.lib_folder_filter is not None:
            raw_papers = [p for p in raw_papers if p["folder_id"] == st.session_state.lib_folder_filter]
    else:
        if st.session_state.lib_folder_filter is not None:
            raw_papers = get_papers_in_folder(st.session_state.lib_folder_filter)
        else:
            raw_papers = get_all_papers()
        if q:
            raw_papers = [p for p in raw_papers if q.lower() in p["title"].lower()]

    # Sort
    if st.session_state.lib_sort == "title":
        raw_papers = sorted(raw_papers, key=lambda p: p["title"].lower())
    elif st.session_state.lib_sort == "folder":
        raw_papers = sorted(raw_papers, key=lambda p: (folder_map.get(p["folder_id"]) or "", p["title"].lower()))
    else:  # date
        raw_papers = sorted(raw_papers, key=lambda p: p["created_at"] or "", reverse=True)

    # ── Delete confirmation ───────────────────────────────────────────────────
    if st.session_state.pending_delete_paper:
        dpid = st.session_state.pending_delete_paper
        dp   = next((p for p in raw_papers if p["id"] == dpid), None)
        if dp:
            st.warning(f'Delete **{dp["title"]}**? This cannot be undone.')
            dc1, dc2, _ = st.columns([1, 1, 6])
            with dc1:
                if st.button("Yes, delete", type="primary"):
                    delete_paper(dpid)
                    st.session_state.pending_delete_paper = None
                    st.rerun()
            with dc2:
                if st.button("Cancel"):
                    st.session_state.pending_delete_paper = None
                    st.rerun()

    # Folder delete confirmation
    if st.session_state.pending_delete_folder:
        dfid = st.session_state.pending_delete_folder
        df   = next((f for f in all_folders if f["id"] == dfid), None)
        if df:
            st.warning(f'Delete folder **{df["name"]}**? Papers inside will move to Root.')
            dfc1, dfc2, _ = st.columns([1, 1, 6])
            with dfc1:
                if st.button("Yes, delete folder", type="primary"):
                    delete_folder(dfid)
                    st.session_state.pending_delete_folder = None
                    st.rerun()
            with dfc2:
                if st.button("Cancel##folder"):
                    st.session_state.pending_delete_folder = None
                    st.rerun()

    # ── Paper table ───────────────────────────────────────────────────────────
    if not raw_papers:
        if q or st.session_state.lib_folder_filter:
            st.info("No papers match the current filter.")
        else:
            st.info("No papers in the library yet. Upload a PDF from the sidebar.")
    else:
        # Column headers
        th1, th2, th3, th4 = st.columns([7, 1.2, 0.8, 0.4])
        th1.markdown("**Title**")
        th2.markdown("**Folder**")
        th3.markdown("**Added**")
        th4.markdown("")
        st.markdown('<hr style="margin:2px 0 6px 0">', unsafe_allow_html=True)

        for paper in raw_papers:
            fname    = folder_map.get(paper["folder_id"], "") or "Root"
            date_str = (paper["created_at"] or "")[:10] if paper["created_at"] else ""

            pc1, pc2, pc3, pc4 = st.columns([7, 1.2, 0.8, 0.4], vertical_alignment="center")
            with pc1:
                st.markdown(
                    f'📄 <a href="?open_paper={paper["id"]}" target="_self"'
                    f' style="text-decoration:none;color:inherit">{paper["title"]}</a>',
                    unsafe_allow_html=True,
                )
            with pc2:
                st.caption(fname)
            with pc3:
                st.caption(date_str)
            with pc4:
                st.markdown(
                    f'<a href="?del_paper={paper["id"]}" target="_self" '
                    f'style="text-decoration:none;font-size:1.1em;cursor:pointer" '
                    f'title="Delete paper">🗑</a>',
                    unsafe_allow_html=True,
                )


else:
    paper = get_paper(st.session_state.selected_paper_id)
    if paper is None:
        st.session_state.selected_paper_id = None
        st.rerun()

    if st.button("← Back to library"):
        st.session_state.selected_paper_id = None
        st.rerun()

    # ── Title (with inline rename) ────────────────────────────────────────────
    if st.session_state.editing_title:
        with st.form("rename_form"):
            new_title = st.text_input("Title", value=paper["title"])
            c1, c2 = st.columns(2)
            with c1:
                if st.form_submit_button("Save", type="primary"):
                    if new_title.strip():
                        rename_paper(paper["id"], new_title.strip())
                    st.session_state.editing_title = False
                    st.rerun()
            with c2:
                if st.form_submit_button("Cancel"):
                    st.session_state.editing_title = False
                    st.rerun()
    else:
        col_t, col_rename = st.columns([9, 1])
        with col_t:
            st.title(paper["title"])
            st.caption(paper["filename"])
            meta = extract_metadata(Path(paper["md_path"]).read_text(encoding="utf-8"))
            if meta["authors"]:
                st.markdown(f"*{meta['authors']}*")
            if meta["doi"] or meta["pmid"]:
                parts = []
                if meta["doi"]:
                    parts.append(f"DOI: `{meta['doi']}`")
                if meta["pmid"]:
                    parts.append(f"PMID: `{meta['pmid']}`")
                st.caption(" · ".join(parts))
        with col_rename:
            if st.button("✏ Rename", use_container_width=True):
                st.session_state.editing_title = True
                st.rerun()

    # ── Tags row ──────────────────────────────────────────────────────────────
    paper_tags = get_paper_tags(paper["id"])
    col_tags, col_tag_btn = st.columns([8, 2])
    with col_tags:
        if paper_tags:
            st.markdown(_tag_badges(paper_tags), unsafe_allow_html=True)
        else:
            st.caption("No tags")
    with col_tag_btn:
        if st.button("Manage tags", use_container_width=True):
            st.session_state.show_tag_manager = not st.session_state.show_tag_manager

    if st.session_state.show_tag_manager:
        all_tags = get_all_tags()
        paper_tag_ids = {t["id"] for t in paper_tags}

        with st.container(border=True):
            st.caption("**Tags on this paper** — click to remove")
            if paper_tags:
                for tag in paper_tags:
                    if st.button(f"✕ {tag['name']}", key=f"rm_tag_{tag['id']}"):
                        remove_paper_tag(paper["id"], tag["id"])
                        st.rerun()
            else:
                st.caption("None")

            unassigned = [t for t in all_tags if t["id"] not in paper_tag_ids]
            if unassigned:
                st.caption("**Add a tag**")
                for tag in unassigned:
                    if st.button(
                        tag["name"], key=f"add_tag_{tag['id']}",
                        help=f'Add "{tag["name"]}"',
                    ):
                        add_paper_tag(paper["id"], tag["id"])
                        st.rerun()

            st.caption("**Create new tag**")
            with st.form("new_tag_form", clear_on_submit=True):
                tc1, tc2, tc3 = st.columns([3, 2, 1])
                with tc1:
                    new_tag_name = st.text_input("Name", label_visibility="collapsed",
                                                 placeholder="Tag name")
                with tc2:
                    color_choice = st.selectbox("Color", list(TAG_COLORS.keys()),
                                                label_visibility="collapsed")
                with tc3:
                    if st.form_submit_button("Add"):
                        if new_tag_name.strip():
                            tid = create_tag(new_tag_name.strip(), TAG_COLORS[color_choice])
                            add_paper_tag(paper["id"], tid)
                            st.rerun()

    st.divider()

    # ── Move + Download row ───────────────────────────────────────────────────
    pid = paper["id"]
    mp3_state = st.session_state.mp3_cache.get(pid)  # None | "processing" | bytes

    # Run MP3 generation before rendering the row so the spinner is visible
    if mp3_state == "processing":
        with st.spinner("Generating MP3 — this may take a minute…"):
            mp3_bytes = markdown_to_mp3(Path(paper["md_path"]).read_text(encoding="utf-8"))
        st.session_state.mp3_cache[pid] = mp3_bytes
        st.rerun()

    folders = get_all_folders()
    folder_map = {f["id"]: f["name"] for f in folders}
    folder_opts = [None] + [f["id"] for f in folders]
    current_idx = folder_opts.index(paper["folder_id"]) if paper["folder_id"] in folder_opts else 0

    mp3_filename = Path(paper["filename"]).stem + ".mp3"
    md_filename  = Path(paper["filename"]).stem + ".md"

    rc_move, rc3, rc4, rc5 = st.columns([3, 1, 1, 1])

    with rc_move:
        mv1, mv2 = st.columns([3, 1])
        with mv1:
            new_folder = st.selectbox(
                "Move to folder",
                options=folder_opts,
                format_func=lambda x: "Root" if x is None else folder_map[x],
                index=current_idx,
                label_visibility="collapsed",
                key="move_folder_sel",
            )
        with mv2:
            if st.button("Move", use_container_width=True):
                move_paper(paper["id"], new_folder)
                st.rerun()
    with rc3:
        with open(paper["pdf_path"], "rb") as f:
            st.download_button(
                "⬇ PDF",
                data=f.read(),
                file_name=paper["filename"],
                mime="application/pdf",
                use_container_width=True,
            )
    with rc4:
        st.download_button(
            "⬇ MD",
            data=Path(paper["md_path"]).read_text(encoding="utf-8"),
            file_name=md_filename,
            mime="text/markdown",
            use_container_width=True,
        )
    with rc5:
        if mp3_state is None:
            if st.button("🔊 MP3", use_container_width=True):
                st.session_state.mp3_cache[pid] = "processing"
                st.rerun()
        else:
            st.download_button(
                "⬇ MP3",
                data=mp3_state,
                file_name=mp3_filename,
                mime="audio/mpeg",
                use_container_width=True,
            )
            if st.button("↺ MP3", use_container_width=True, help="Regenerate MP3"):
                del st.session_state.mp3_cache[pid]
                st.rerun()

    st.divider()

    # ── Reading modes ─────────────────────────────────────────────────────────
    md_content = Path(paper["md_path"]).read_text(encoding="utf-8")
    md_path = paper["md_path"]

    # Run pending generation before rendering tabs so the spinner is visible
    if st.session_state.generating_summary:
        with st.spinner("Generating summary — this may take a moment…"):
            generate_summary(md_content, md_path)
        st.session_state.generating_summary = False
        st.rerun()

    if st.session_state.generating_news:
        with st.spinner("Generating news article — this may take a moment…"):
            generate_news(md_content, md_path)
        st.session_state.generating_news = False
        st.rerun()

    tab_md, tab_summary, tab_news = st.tabs(["Markdown", "Summary", "News Article"])

    with tab_md:
        st.markdown(md_content)

    with tab_summary:
        if summary_exists(md_path):
            meta = get_summary_meta(md_path)
            if meta:
                st.caption(
                    f"Summarizer v{meta.get('version', '?')} · "
                    f"Generated {meta.get('generated_at', '')[:10]}"
                )
            st.markdown(load_summary(md_path))
            if st.button("↺ Regenerate summary", key="regen_summary"):
                clear_summary(md_path)
                st.session_state.generating_summary = True
                st.rerun()
        else:
            st.info("No summary yet.")
            if st.button("Generate Summary", type="primary", key="gen_summary"):
                st.session_state.generating_summary = True
                st.rerun()

    with tab_news:
        if news_exists(md_path):
            meta = get_news_meta(md_path)
            if meta:
                st.caption(
                    f"Summarizer v{meta.get('version', '?')} · "
                    f"Generated {meta.get('generated_at', '')[:10]}"
                )
            st.markdown(load_news(md_path))
            if st.button("↺ Regenerate news article", key="regen_news"):
                clear_news(md_path)
                st.session_state.generating_news = True
                st.rerun()
        else:
            st.info("No news article yet.")
            if st.button("Generate News Article", type="primary", key="gen_news"):
                st.session_state.generating_news = True
                st.rerun()

    st.divider()

    # ── Content search within this paper ─────────────────────────────────────
    with st.expander("Search in this paper's content"):
        with st.form("paper_content_search"):
            sq = st.text_input("Keyword", label_visibility="collapsed", placeholder="Keyword…")
            if st.form_submit_button("Find"):
                if sq.strip():
                    hits = [ln for ln in md_content.splitlines() if sq.lower() in ln.lower()]
                    if hits:
                        st.write(f'**{len(hits)} line(s) matching "{sq}":**')
                        for line in hits[:50]:
                            st.markdown(f"> {line.strip()}")
                    else:
                        st.info("No matches found.")

    st.divider()

    # ── Notes ─────────────────────────────────────────────────────────────────
    st.subheader("Notes")

    with st.form("add_note_form", clear_on_submit=True):
        note_text = st.text_area(
            "New note",
            placeholder="Add observations, annotations, or reminders…",
            label_visibility="collapsed",
        )
        if st.form_submit_button("Save Note"):
            if note_text.strip():
                add_comment(paper["id"], note_text.strip())
                st.rerun()

    for comment in get_comments(paper["id"]):
        cid     = comment["id"]
        editing = st.session_state.editing_comment_id == cid

        with st.container(border=True):
            if editing:
                updated = st.text_area("Edit note", value=comment["content"], key=f"edit_ta_{cid}")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Save", key=f"save_note_{cid}", type="primary", use_container_width=True):
                        if updated.strip():
                            update_comment(cid, updated.strip())
                        st.session_state.editing_comment_id = None
                        st.rerun()
                with c2:
                    if st.button("Cancel", key=f"cancel_note_{cid}", use_container_width=True):
                        st.session_state.editing_comment_id = None
                        st.rerun()
            else:
                st.write(comment["content"])
                c1, c2, c3 = st.columns([6, 1, 1])
                with c1:
                    st.caption(f"Saved: {comment['created_at']}")
                with c2:
                    if st.button("Edit", key=f"edit_note_{cid}", use_container_width=True):
                        st.session_state.editing_comment_id = cid
                        st.rerun()
                with c3:
                    if st.button("Delete", key=f"dc_{cid}", use_container_width=True):
                        delete_comment(cid)
                        st.rerun()
