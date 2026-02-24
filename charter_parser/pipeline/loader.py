"""
PDF loading: Docling for layout structure, pdfplumber for strikethrough detection.
"""

import logging
from collections import defaultdict
from pathlib import Path

import pdfplumber

from charter_parser.state import DocumentElement

logger = logging.getLogger(__name__)

_X_BUCKET_SIZE = 10     # x-coordinate bucketing resolution (points)
_MAX_RECT_HEIGHT = 3    # strikethrough rects are very thin
_MIN_RECT_WIDTH = 50    # skip small decorative marks


def _detect_strikethrough_text(pdf_path: str) -> dict[int, set[str]]:
    """Find struck-through text by matching thin horizontal rects against character positions."""
    struck: dict[int, set[str]] = defaultdict(set)

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            strike_rects = [
                r for r in page.rects
                if abs(r["bottom"] - r["top"]) < _MAX_RECT_HEIGHT
                and abs(r["x1"] - r["x0"]) > _MIN_RECT_WIDTH
            ]
            if not strike_rects:
                continue

            chars = page.chars
            for rect in strike_rects:
                ry = rect["top"]
                rx0 = rect["x0"]
                rx1 = rect["x1"]

                struck_chars = []
                for char in chars:
                    char_height = char["bottom"] - char["top"]
                    char_mid_top = char["top"] + char_height * 0.2
                    char_mid_bot = char["top"] + char_height * 0.8

                    if (char_mid_top <= ry <= char_mid_bot
                            and char["x0"] >= rx0 - 2
                            and char["x1"] <= rx1 + 2):
                        struck_chars.append(char["text"])

                if struck_chars:
                    struck[page_num].add("".join(struck_chars).strip())

    return dict(struck)


def _is_text_struck(text: str, page: int, struck_text: dict[int, set[str]]) -> bool:
    """True if more than half the element's text overlaps with struck-through fragments."""
    fragments = struck_text.get(page, set())
    if not fragments:
        return False

    normalized = " ".join(text.split()).lower()
    matched_chars = 0
    for fragment in fragments:
        norm_frag = " ".join(fragment.split()).lower()
        if len(norm_frag) < 5:
            continue
        if norm_frag in normalized:
            matched_chars += len(norm_frag)

    return matched_chars > len(normalized) * 0.5


def _detect_margin_notes(raw_items: list[dict]) -> set[int]:
    """Tag margin notes in two-column layouts using bounding box positions.

    Per page: find the main content column (x-bucket with most text),
    then flag elements whose right edge doesn't reach it.
    """
    by_page: dict[int, list[int]] = defaultdict(list)
    for i, item in enumerate(raw_items):
        if item["x0"] > 0:
            by_page[item["page"]].append(i)

    margin_indices: set[int] = set()

    for page, indices in by_page.items():
        if len(indices) < 3:
            continue

        bucket_text: dict[int, int] = defaultdict(int)
        for i in indices:
            bucket = int(raw_items[i]["x0"] / _X_BUCKET_SIZE) * _X_BUCKET_SIZE
            bucket_text[bucket] += len(raw_items[i]["text"])

        main_x = max(bucket_text, key=bucket_text.get)

        candidates = []
        for i in indices:
            if raw_items[i]["x0"] < main_x:
                right_edge = raw_items[i]["x0"] + raw_items[i]["width"]
                if right_edge < main_x:
                    candidates.append(i)

        if len(candidates) >= 2:
            margin_indices.update(candidates)

    return margin_indices


def load_document(state: dict) -> dict:
    """Convert PDF to structured elements. Filters strikethrough, tags margin notes."""
    from docling.document_converter import DocumentConverter

    pdf_path = state["pdf_path"]
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Strikethrough scan (pdfplumber geometry)
    logger.info("Scanning for strikethrough: %s", pdf_path)
    struck_text = _detect_strikethrough_text(str(path))
    struck_total = sum(len(v) for v in struck_text.values())
    if struck_total:
        logger.info("Found %d struck-through fragments across %d pages", struck_total, len(struck_text))

    # Layout extraction (Docling)
    logger.info("Converting with Docling: %s", pdf_path)
    doc = DocumentConverter().convert(str(path)).document

    raw_items: list[dict] = []
    struck_count = 0
    for item, level in doc.iterate_items():
        if not hasattr(item, "text") or not item.text:
            continue

        page = 0
        x0 = 0.0
        width = 0.0
        if hasattr(item, "prov") and item.prov:
            page = item.prov[0].page_no
            bbox = item.prov[0].bbox
            x0 = bbox.l
            width = bbox.r - bbox.l

        if _is_text_struck(item.text, page, struck_text):
            struck_count += 1
            continue

        raw_items.append({
            "label": (item.label.value if hasattr(item.label, "value") else str(item.label)).upper(),
            "text": item.text.strip(),
            "page": page,
            "level": level or 0,
            "x0": x0,
            "width": width,
        })

    if struck_count:
        logger.info("Filtered %d struck-through elements", struck_count)

    margin_indices = _detect_margin_notes(raw_items)

    elements = [
        DocumentElement(
            label=item["label"],
            text=item["text"],
            page=item["page"],
            level=item["level"],
            is_margin_note=(i in margin_indices),
        )
        for i, item in enumerate(raw_items)
    ]

    if margin_indices:
        logger.info("Tagged %d elements as margin notes", len(margin_indices))
    logger.info("Loaded %d elements", len(elements))
    return {"elements": elements}
