"""
Extract individual clauses using Sonnet. One LLM call per clause, all concurrent.
"""

import asyncio
import json
import logging
import re
from typing import Any

import anthropic

from charter_parser.state import SectionData

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

EXTRACT_PROMPT = """\
You are extracting a single clause from a maritime charter party document.

Extract clause number {number} ONLY. Do not include content from other clauses.

Rules:
1. "title" — the clause heading in plain text, no markdown.
   If the heading sits beside the number (e.g. "Condition Of vessel  1."),
   use the heading text only.
2. "text" — the complete operative clause body including all sub-clauses
   (a), (b), (i), (ii). Preserve paragraph structure with \\n\\n.
   Strip markdown characters (**, *, ##, _) — plain prose only.

Return a single JSON object:
{{
  "number": {number},
  "title": "...",
  "text": "..."
}}

DOCUMENT SECTION — {section_title}:
---
{text}
---

Return ONLY the JSON object."""


async def _extract_single(
    client: anthropic.AsyncAnthropic,
    section: SectionData,
    number: int,
) -> dict[str, Any]:
    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": EXTRACT_PROMPT.format(
                    number=number,
                    section_title=section["title"],
                    text=section["text"],
                )
            }]
        )
        raw = _FENCE_RE.sub("", response.content[0].text).strip()
        data = json.loads(raw)
        data["section_index"] = section["index"]
        return data

    except Exception as exc:
        logger.error("Extraction failed for %s clause %d: %s", section["title"], number, exc)
        return {
            "number": number,
            "title": f"Clause {number}",
            "text": "",
            "section_index": section["index"],
        }


async def _extract_section(
    section: SectionData,
    clause_numbers: list[int],
) -> list[dict[str, Any]]:
    client = anthropic.AsyncAnthropic()
    tasks = [_extract_single(client, section, n) for n in clause_numbers]
    return list(await asyncio.gather(*tasks))


def extract_clauses(state: dict) -> dict:
    sections = state["sections"]
    clause_index = state["clause_index"]
    all_clauses: list[dict[str, Any]] = []

    for section in sections:
        numbers = clause_index.get(section["title"], [])
        if not numbers:
            logger.warning("No clauses enumerated for %r", section["title"])
            continue

        logger.info("Extracting %d clauses from %r", len(numbers), section["title"])
        clauses = asyncio.run(_extract_section(section, numbers))
        all_clauses.extend(clauses)
        logger.info("  Done: %d clauses", len(clauses))

    return {"raw_clauses": all_clauses}
