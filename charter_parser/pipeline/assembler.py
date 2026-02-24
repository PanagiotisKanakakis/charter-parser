"""
pipeline/assembler.py — final assembly and validation.

Ordering is deterministic: sort by (section_index, clause_number).
No LLM involved. Pure Python.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def assemble(state: dict) -> dict:
    """Sort clauses in document order, produce final output."""
    raw_clauses = state.get("raw_clauses", [])

    ordered = sorted(
        raw_clauses,
        key=lambda c: (c.get("section_index", 0), c.get("number", 0)),
    )

    clauses: list[dict[str, Any]] = []
    for raw in ordered:
        text = raw.get("agreed_text", "").strip()
        if not text:
            continue
        clauses.append({
            "id": str(raw.get("number", "")),
            "title": raw.get("title", ""),
            "text": text,
        })

    logger.info("Assembly complete: %d clauses", len(clauses))
    return {"clauses": clauses}
