import re


def convert_pdf_to_markdown(pdf_path: str) -> str:
    """Full conversion of a PDF to Markdown — not a summary."""
    import pymupdf4llm
    md_text = pymupdf4llm.to_markdown(str(pdf_path))
    return _clean_markdown(md_text)


def _clean_markdown(text: str) -> str:
    """Remove PDF-specific artifacts from converted text."""
    # Fix hyphenated line-breaks (PDFs often split words across lines)
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
    # Collapse runs of 3+ blank lines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove null bytes and non-printable control characters (keep \t \n)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    # Expand common ligature glyphs missed by the extractor
    for src, dst in [('ﬁ', 'fi'), ('ﬂ', 'fl'), ('ﬀ', 'ff'),
                     ('ﬃ', 'ffi'), ('ﬄ', 'ffl'), ('ﬅ', 'st')]:
        text = text.replace(src, dst)
    return text.strip()
