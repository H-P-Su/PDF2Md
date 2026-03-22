import shutil
from pathlib import Path

from services.db import get_connection

FILES_DIR = Path("storage/files")

TAG_COLORS = {
    "Blue":   "#4A90D9",
    "Green":  "#27AE60",
    "Orange": "#E67E22",
    "Red":    "#E74C3C",
    "Purple": "#8E44AD",
    "Teal":   "#16A085",
    "Gray":   "#7F8C8D",
    "Pink":   "#D63C8E",
}


def _paper_dir(paper_id: int) -> Path:
    return FILES_DIR / str(paper_id)


def _sort_clause(sort: str) -> str:
    return "title COLLATE NOCASE" if sort == "title" else "created_at DESC"


# ── Papers ────────────────────────────────────────────────────────────────────

def save_paper(
    title: str,
    filename: str,
    pdf_bytes: bytes,
    md_content: str,
    folder_id: int | None = None,
) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO papers (title, filename, folder_id, pdf_path, md_path) VALUES (?, ?, ?, '', '')",
        (title, filename, folder_id),
    )
    paper_id = cur.lastrowid

    paper_dir = _paper_dir(paper_id)
    paper_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = paper_dir / "paper.pdf"
    md_path  = paper_dir / "paper.md"
    pdf_path.write_bytes(pdf_bytes)
    md_path.write_text(md_content, encoding="utf-8")

    conn.execute(
        "UPDATE papers SET pdf_path = ?, md_path = ? WHERE id = ?",
        (str(pdf_path), str(md_path), paper_id),
    )
    conn.commit()
    conn.close()
    return paper_id


def get_paper(paper_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    conn.close()
    return row


def get_papers_in_folder(folder_id: int | None, sort: str = "title"):
    order = _sort_clause(sort)
    conn = get_connection()
    if folder_id is None:
        rows = conn.execute(
            f"SELECT * FROM papers WHERE folder_id IS NULL ORDER BY {order}"
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT * FROM papers WHERE folder_id = ? ORDER BY {order}",
            (folder_id,),
        ).fetchall()
    conn.close()
    return rows


def paper_exists(filename: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT id FROM papers WHERE filename = ?", (filename,)).fetchone()
    conn.close()
    return row is not None


def register_external_paper(
    title: str,
    filename: str,
    pdf_path: str,
    md_path: str,
    folder_id: int | None = None,
) -> int:
    """Register a paper that already exists on disk without copying files.

    Returns the new paper_id, or the existing paper_id if already registered.
    """
    conn = get_connection()
    existing = conn.execute(
        "SELECT id, folder_id FROM papers WHERE filename = ?", (filename,)
    ).fetchone()
    if existing:
        # Move to the target folder if not already there
        if folder_id is not None and existing["folder_id"] != folder_id:
            conn.execute(
                "UPDATE papers SET folder_id = ? WHERE id = ?",
                (folder_id, existing["id"]),
            )
            conn.commit()
        conn.close()
        return existing["id"]
    cur = conn.execute(
        "INSERT INTO papers (title, filename, folder_id, pdf_path, md_path) "
        "VALUES (?, ?, ?, ?, ?)",
        (title, filename, folder_id, pdf_path, md_path),
    )
    paper_id = cur.lastrowid
    conn.commit()
    conn.close()
    return paper_id


def get_folder_by_name(name: str):
    """Return the folder row with the given name, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM folders WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    conn.close()
    return row


def get_or_create_folder(name: str) -> int:
    """Return the id of the named folder, creating it if it doesn't exist."""
    row = get_folder_by_name(name)
    if row:
        return row["id"]
    return create_folder(name)


def rename_paper(paper_id: int, new_title: str):
    conn = get_connection()
    conn.execute("UPDATE papers SET title = ? WHERE id = ?", (new_title, paper_id))
    conn.commit()
    conn.close()


def move_paper(paper_id: int, folder_id: int | None):
    conn = get_connection()
    conn.execute("UPDATE papers SET folder_id = ? WHERE id = ?", (folder_id, paper_id))
    conn.commit()
    conn.close()


def delete_paper(paper_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    conn.commit()
    conn.close()
    paper_dir = _paper_dir(paper_id)
    if paper_dir.exists():
        shutil.rmtree(paper_dir)


def search_papers_by_title(query: str, sort: str = "title"):
    order = _sort_clause(sort)
    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM papers WHERE LOWER(title) LIKE ? ORDER BY {order}",
        (f"%{query.lower()}%",),
    ).fetchall()
    conn.close()
    return rows


def search_papers_by_content(query: str) -> list:
    """Scan all markdown files for query string. Returns matching paper rows."""
    conn = get_connection()
    all_papers = conn.execute("SELECT * FROM papers").fetchall()
    conn.close()

    query_lower = query.lower()
    results = []
    for paper in all_papers:
        try:
            content = Path(paper["md_path"]).read_text(encoding="utf-8")
            if query_lower in content.lower():
                results.append(paper)
        except Exception:
            pass
    return results


# ── Folders ───────────────────────────────────────────────────────────────────

def get_all_folders():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM folders ORDER BY name COLLATE NOCASE").fetchall()
    conn.close()
    return rows


def create_folder(name: str) -> int:
    conn = get_connection()
    cur = conn.execute("INSERT INTO folders (name) VALUES (?)", (name,))
    folder_id = cur.lastrowid
    conn.commit()
    conn.close()
    return folder_id


def delete_folder(folder_id: int):
    """Delete folder; its papers are promoted to root (folder_id → NULL)."""
    conn = get_connection()
    conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
    conn.commit()
    conn.close()


# ── Comments ──────────────────────────────────────────────────────────────────

def get_comments(paper_id: int):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM comments WHERE paper_id = ? ORDER BY created_at DESC",
        (paper_id,),
    ).fetchall()
    conn.close()
    return rows


def add_comment(paper_id: int, content: str):
    conn = get_connection()
    conn.execute("INSERT INTO comments (paper_id, content) VALUES (?, ?)", (paper_id, content))
    conn.commit()
    conn.close()


def update_comment(comment_id: int, content: str):
    conn = get_connection()
    conn.execute("UPDATE comments SET content = ? WHERE id = ?", (content, comment_id))
    conn.commit()
    conn.close()


def delete_comment(comment_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    conn.commit()
    conn.close()


# ── Tags ──────────────────────────────────────────────────────────────────────

def get_all_tags():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM tags ORDER BY name COLLATE NOCASE").fetchall()
    conn.close()
    return rows


def create_tag(name: str, color: str) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT OR IGNORE INTO tags (name, color) VALUES (?, ?)", (name, color)
    )
    tag_id = cur.lastrowid
    conn.commit()
    conn.close()
    return tag_id


def delete_tag(tag_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.commit()
    conn.close()


def get_paper_tags(paper_id: int):
    conn = get_connection()
    rows = conn.execute(
        """SELECT t.* FROM tags t
           JOIN paper_tags pt ON pt.tag_id = t.id
           WHERE pt.paper_id = ?
           ORDER BY t.name COLLATE NOCASE""",
        (paper_id,),
    ).fetchall()
    conn.close()
    return rows


def add_paper_tag(paper_id: int, tag_id: int):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO paper_tags (paper_id, tag_id) VALUES (?, ?)",
        (paper_id, tag_id),
    )
    conn.commit()
    conn.close()


def remove_paper_tag(paper_id: int, tag_id: int):
    conn = get_connection()
    conn.execute(
        "DELETE FROM paper_tags WHERE paper_id = ? AND tag_id = ?",
        (paper_id, tag_id),
    )
    conn.commit()
    conn.close()
