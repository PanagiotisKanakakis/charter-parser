"""Sort clauses in document order and produce final output."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def assemble(state: dict) -> dict:
    raw_clauses = state.get("raw_clauses", [])

    ordered = sorted(
        raw_clauses,
        key=lambda c: (c.get("section_index", 0), c.get("number", 0)),
    )

    clauses: list[dict[str, Any]] = []
    for raw in ordered:
        text = raw.get("text", "").strip()
        if not text:
            continue
        clauses.append({
            "id": str(raw.get("number", "")),
            "title": raw.get("title", ""),
            "text": text,
        })

    logger.info("Assembly complete: %d clauses", len(clauses))
    return {"clauses": clauses}
