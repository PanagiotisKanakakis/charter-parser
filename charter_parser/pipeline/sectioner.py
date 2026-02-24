"""
Groups document elements into sections by detecting clause numbering restarts.

When clause numbers jump from e.g. 43 back to 1 and there's a title header
nearby, that's a section boundary. Works without hardcoded section names.
"""

import logging
import re

from charter_parser.state import DocumentElement, SectionData

logger = logging.getLogger(__name__)

_LEADING_NUMBER_RE = re.compile(r"^\s*(\d+)\s*\.")


def _extract_leading_number(text: str) -> int | None:
    m = _LEADING_NUMBER_RE.match(text)
    return int(m.group(1)) if m else None


def _elements_to_text(elements: list[DocumentElement]) -> str:
    """Join element texts, skipping margin notes."""
    parts = []
    for el in elements:
        if el.get("is_margin_note", False):
            continue
        if el["label"] in ("TEXT", "LIST_ITEM", "SECTION_HEADER"):
            text = el["text"].strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def _find_title_header(
    elements: list[DocumentElement], before_idx: int, after_idx: int,
) -> tuple[str, int] | None:
    """Look backwards for a non-numbered SECTION_HEADER (the section title)."""
    for i in range(before_idx, max(after_idx, before_idx - 10), -1):
        el = elements[i]
        if el.get("is_margin_note", False):
            continue
        if el["label"] == "SECTION_HEADER":
            if _extract_leading_number(el["text"]) is None and len(el["text"]) > 5:
                return (el["text"].strip(), i)
    return None


def discover_sections(state: dict) -> dict:
    """Split elements into sections based on clause numbering restarts."""
    elements = state["elements"]

    if not elements:
        return {"sections": []}

    # Find numbered headers
    numbered_headers: list[tuple[int, int]] = []
    for i, el in enumerate(elements):
        if el["label"] == "SECTION_HEADER" and not el.get("is_margin_note", False):
            num = _extract_leading_number(el["text"])
            if num is not None:
                numbered_headers.append((i, num))

    logger.info("Found %d numbered section headers", len(numbered_headers))

    # Detect numbering restarts (must have a title header between prev and curr)
    boundaries: list[tuple[str, int]] = []

    for j in range(1, len(numbered_headers)):
        prev_idx, prev_num = numbered_headers[j - 1]
        curr_idx, curr_num = numbered_headers[j]

        if curr_num > 2 or prev_num <= curr_num:
            continue

        found = _find_title_header(elements, curr_idx - 1, prev_idx)
        if found:
            title, title_idx = found
            boundaries.append((title, title_idx))
            logger.info(
                "Section boundary: %r at element %d (restart %d -> %d)",
                title, title_idx, prev_num, curr_num,
            )

    # Build sections
    sections: list[SectionData] = []

    if not boundaries:
        sections.append(SectionData(
            title="Main Clauses",
            index=0,
            elements=elements,
            text=_elements_to_text(elements),
        ))
    else:
        first_boundary_idx = boundaries[0][1]
        body_elements = elements[:first_boundary_idx]
        if body_elements:
            sections.append(SectionData(
                title="Main Clauses",
                index=0,
                elements=body_elements,
                text=_elements_to_text(body_elements),
            ))

        for k, (title, start_idx) in enumerate(boundaries):
            end_idx = boundaries[k + 1][1] if k + 1 < len(boundaries) else len(elements)
            sec_elements = elements[start_idx:end_idx]
            sections.append(SectionData(
                title=title,
                index=k + 1,
                elements=sec_elements,
                text=_elements_to_text(sec_elements),
            ))

    for s in sections:
        logger.info(
            "  Section [%d] %r %d chars",
            s["index"], s["title"], len(s["text"]),
        )
    logger.info("Discovered %d sections", len(sections))
    return {"sections": sections}
