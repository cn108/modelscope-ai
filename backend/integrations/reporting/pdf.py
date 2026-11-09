"""Small, dependency-free PDF renderer for analytics reports.

The exports are intentionally plain: labelled text sections on A4 pages, with
page numbers and wrapped lines.  This keeps report generation deterministic and
avoids adding a PDF runtime to the API image just for summaries.
"""

from __future__ import annotations

import textwrap

PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
MARGIN = 48.0
TOP = PAGE_HEIGHT - 54
BOTTOM = 52.0
MAX_WIDTH = PAGE_WIDTH - (MARGIN * 2)


def _escape(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


_ASCII_TRANSLATION = str.maketrans(
    {
        "–": "-",
        "—": "-",
        "·": "|",
        "•": "-",
        "…": "...",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
    }
)


def _wrap(text: str, size: float) -> list[str]:
    # Helvetica's average glyph width is close to half the font size.  A
    # conservative divisor leaves room for wide characters and margins.
    character_width = max(size * 0.53, 1)
    width = max(int(MAX_WIDTH / character_width), 20)
    plain = str(text or "").translate(_ASCII_TRANSLATION)
    plain = plain.encode("latin-1", "replace").decode("latin-1")
    lines = textwrap.wrap(
        " ".join(plain.split()),
        width=width,
        break_long_words=True,
        break_on_hyphens=False,
    )
    return lines or [""]


def _document_lines(document: dict) -> list[dict]:
    blocks: list[dict] = []

    def add(text: str, *, size: float, bold: bool = False, gap: float = 2.0):
        wrapped = _wrap(text, size)
        for index, line in enumerate(wrapped):
            blocks.append(
                {
                    "text": line,
                    "size": size,
                    "bold": bold,
                    "gap": gap if index == len(wrapped) - 1 else 0.0,
                    "height": size * 1.35,
                }
            )

    add("ModelScope AI", size=9, gap=4)
    add(document.get("title", "Analytics report"), size=17, bold=True, gap=10)
    for label, value in document.get("metadata", []):
        add(f"{label}: {value}", size=9.2, gap=2.5)

    for section in document.get("sections", []):
        add(section.get("title", "Section"), size=12.5, bold=True, gap=4)
        for label, value in section.get("rows", []):
            add(f"{label}: {value}", size=9.2, gap=2.5)

    notes = document.get("notes") or []
    if notes:
        add("Limitations", size=12.5, bold=True, gap=4)
        for note in notes:
            add(f"• {note}", size=9.2, gap=2.5)
    return blocks


def _paginate(blocks: list[dict]) -> list[list[dict]]:
    pages: list[list[dict]] = [[]]
    y = TOP
    for block in blocks:
        height = block["height"] + block["gap"]
        if pages[-1] and y - height < BOTTOM:
            pages.append([])
            y = TOP
        pages[-1].append({**block, "y": y})
        y -= height
    return pages


def _content(page: list[dict], page_number: int, total_pages: int) -> bytes:
    commands = ["BT"]
    for line in page:
        font = "F2" if line["bold"] else "F1"
        commands.append(f"/{font} {line['size']:.2f} Tf")
        commands.append(
            f"1 0 0 1 {MARGIN:.2f} {line['y']:.2f} Tm ({_escape(line['text'])}) Tj"
        )
    commands.append("ET")
    commands.append("0.75 w 0.85 0.88 0.92 RG")
    commands.append(f"{MARGIN:.2f} 39 m {PAGE_WIDTH - MARGIN:.2f} 39 l S")
    commands.append("BT /F1 8 Tf 0.45 0.48 0.55 rg")
    commands.append(
        f"1 0 0 1 {MARGIN:.2f} 25 Tm (ModelScope AI | Analytics report | "
        f"Page {page_number} of {total_pages}) Tj"
    )
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", "replace")


def render_pdf(document: dict) -> bytes:
    pages = _paginate(_document_lines(document))
    objects: list[bytes] = []

    def add_object(value: bytes) -> int:
        objects.append(value)
        return len(objects)

    catalog_id = add_object(b"<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add_object(b"")  # filled after page objects are known
    regular_font_id = add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    )
    bold_font_id = add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"
    )

    page_ids = []
    for index, page in enumerate(pages, start=1):
        content = _content(page, index, len(pages))
        content_id = add_object(
            b"<< /Length "
            + str(len(content)).encode("ascii")
            + b" >>\nstream\n"
            + content
            + b"\nendstream"
        )
        page_id = add_object(
            (
                "<< /Type /Page /Parent 2 0 R "
                "/MediaBox [0 0 595.28 841.89] "
                "/Resources << /Font << "
                f"/F1 {regular_font_id} 0 R /F2 {bold_font_id} 0 R "
                ">> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        page_ids.append(page_id)

    objects[pages_id - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{pid} 0 R' for pid in page_ids)}] "
        f"/Count {len(page_ids)} >>"
    ).encode("ascii")
    if catalog_id != 1 or pages_id != 2:  # defensive; keeps catalog references honest
        raise RuntimeError("Unexpected PDF object numbering.")

    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    body = bytearray(header)
    offsets = [0]
    for number, value in enumerate(objects, start=1):
        offsets.append(len(body))
        body.extend(f"{number} 0 obj\n".encode("ascii"))
        body.extend(value)
        body.extend(b"\nendobj\n")

    xref_offset = len(body)
    body.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    body.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(body)
