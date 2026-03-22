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
    save_paper, get_paper, get_papers_in_folder, paper_exists,
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


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("PDF Library")

    # ── Upload ──────────────────────────────────────────────────────────────
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

    st.divider()

    # ── Library header + new-folder button ──────────────────────────────────
    col_hdr, col_new = st.columns([3, 1])
    with col_hdr:
        st.subheader("Library")
    with col_new:
        if st.button("📁+", help="Create new folder"):
            st.session_state.show_new_folder = not st.session_state.show_new_folder

    if st.session_state.show_new_folder:
        with st.form("new_folder_form", clear_on_submit=True):
            folder_name = st.text_input("Folder name")
            if st.form_submit_button("Create"):
                if folder_name.strip():
                    create_folder(folder_name.strip())
                    st.session_state.show_new_folder = False
                    st.rerun()

    # ── Search & sort ────────────────────────────────────────────────────────
    search_q = st.text_input("Search titles…", key="search_q", label_visibility="collapsed",
                             placeholder="Search titles…")
    sort_order = st.radio("Sort by", ["Title A–Z", "Date added"], horizontal=True,
                          label_visibility="collapsed", key="sort_order_radio")
    sort_key = "title" if sort_order == "Title A–Z" else "date"

    # ── Paper row renderer ───────────────────────────────────────────────────
    def _paper_row(paper, folder_label: str = ""):
        pid    = paper["id"]
        active  = st.session_state.selected_paper_id == pid
        pending = st.session_state.pending_delete_paper == pid

        label = paper["title"]
        if len(label) > 26:
            label = label[:25] + "…"

        tags = get_paper_tags(pid)

        if pending:
            st.caption(f'Delete "{paper["title"][:30]}"?')
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Yes, delete", key=f"confirm_dp_{pid}", type="primary", use_container_width=True):
                    delete_paper(pid)
                    if st.session_state.selected_paper_id == pid:
                        st.session_state.selected_paper_id = None
                    st.session_state.pending_delete_paper = None
                    st.rerun()
            with c2:
                if st.button("Cancel", key=f"cancel_dp_{pid}", use_container_width=True):
                    st.session_state.pending_delete_paper = None
                    st.rerun()
        else:
            c1, c2 = st.columns([5, 1])
            with c1:
                prefix = "▶ " if active else ""
                btn_label = f"{prefix}📄 {label}"
                if folder_label:
                    btn_label += f"\n  _{folder_label}_"
                if st.button(btn_label, key=f"p_{pid}", use_container_width=True):
                    _select_paper(pid)
                    st.rerun()
                if tags:
                    st.markdown(_tag_badges(tags, size="0.7em"), unsafe_allow_html=True)
            with c2:
                if st.button("✕", key=f"dp_{pid}", help="Delete"):
                    st.session_state.pending_delete_paper = pid
                    st.rerun()

    # ── Search results or normal tree ────────────────────────────────────────
    if search_q.strip():
        results = search_papers_by_title(search_q.strip(), sort=sort_key)
        if results:
            folder_id_to_name = {f["id"]: f["name"] for f in get_all_folders()}
            for paper in results:
                flabel = folder_id_to_name.get(paper["folder_id"], "") if paper["folder_id"] else ""
                _paper_row(paper, folder_label=flabel)
        else:
            st.caption("No titles match.")
    else:
        # Root papers
        for paper in get_papers_in_folder(None, sort=sort_key):
            _paper_row(paper)

        # Folders
        for folder in get_all_folders():
            fid = folder["id"]
            pending_f = st.session_state.pending_delete_folder == fid

            with st.expander(f"📁 {folder['name']}"):
                for paper in get_papers_in_folder(fid, sort=sort_key):
                    _paper_row(paper)

                if pending_f:
                    st.caption("Delete this folder? Papers will move to Root.")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Yes, delete", key=f"confirm_df_{fid}", type="primary", use_container_width=True):
                            delete_folder(fid)
                            st.session_state.pending_delete_folder = None
                            st.rerun()
                    with c2:
                        if st.button("Cancel", key=f"cancel_df_{fid}", use_container_width=True):
                            st.session_state.pending_delete_folder = None
                            st.rerun()
                else:
                    if st.button("Delete folder", key=f"df_{fid}", type="secondary"):
                        st.session_state.pending_delete_folder = fid
                        st.rerun()


# ── Main panel ────────────────────────────────────────────────────────────────
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

if st.session_state.selected_paper_id is None:
    st.title("PDF Library")
    st.info("Upload a PDF from the sidebar, or select a paper from the library.")

    # Content search from welcome screen
    st.subheader("Search paper content")
    with st.form("content_search_form"):
        cq = st.text_input("Search within all paper text…", label_visibility="collapsed",
                           placeholder="Search within all paper text…")
        if st.form_submit_button("Search"):
            if cq.strip():
                st.session_state.content_search_results = (cq.strip(), search_papers_by_content(cq.strip()))
                st.rerun()

    if st.session_state.content_search_results:
        q, results = st.session_state.content_search_results
        st.write(f'**{len(results)} paper(s) containing "{q}":**')
        for paper in results:
            if st.button(f"📄 {paper['title']}", key=f"cs_{paper['id']}"):
                _select_paper(paper["id"])
                st.rerun()

else:
    paper = get_paper(st.session_state.selected_paper_id)
    if paper is None:
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

    col_move, col_dl = st.columns([3, 3])

    with col_move:
        folders = get_all_folders()
        folder_map = {f["id"]: f["name"] for f in folders}
        folder_opts = [None] + [f["id"] for f in folders]
        current_idx = folder_opts.index(paper["folder_id"]) if paper["folder_id"] in folder_opts else 0

        with st.form("move_form"):
            new_folder = st.selectbox(
                "Move to folder",
                options=folder_opts,
                format_func=lambda x: "Root" if x is None else folder_map[x],
                index=current_idx,
            )
            if st.form_submit_button("Move"):
                move_paper(paper["id"], new_folder)
                st.rerun()

    with col_dl:
        dl1, dl2, dl3 = st.columns(3)
        with dl1:
            with open(paper["pdf_path"], "rb") as f:
                st.download_button(
                    "⬇ Download PDF",
                    data=f.read(),
                    file_name=paper["filename"],
                    mime="application/pdf",
                    use_container_width=True,
                )
        with dl2:
            md_filename = Path(paper["filename"]).stem + ".md"
            st.download_button(
                "⬇ Download MD",
                data=Path(paper["md_path"]).read_text(encoding="utf-8"),
                file_name=md_filename,
                mime="text/markdown",
                use_container_width=True,
            )
        with dl3:
            mp3_filename = Path(paper["filename"]).stem + ".mp3"
            if mp3_state is None:
                if st.button("🔊 Generate MP3", use_container_width=True):
                    st.session_state.mp3_cache[pid] = "processing"
                    st.rerun()
            else:
                st.download_button(
                    "⬇ Download MP3",
                    data=mp3_state,
                    file_name=mp3_filename,
                    mime="audio/mpeg",
                    use_container_width=True,
                )
                if st.button("↺ Redo MP3", use_container_width=True, help="Regenerate MP3"):
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
