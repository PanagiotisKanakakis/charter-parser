"""
Pass 2: extract individual clauses using Sonnet.

One LLM call per clause, all concurrent within each section.
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
2. "agreed_text" — the complete operative clause body including all sub-clauses
   (a), (b), (i), (ii). Preserve paragraph structure with \\n\\n.
   Strip markdown characters (**, *, ##, _) — plain prose only.
3. "sub_clauses" — if the clause has explicitly labelled sub-clauses
   list them separately. Otherwise [].
4. "status" — one of:
   "unamended"  standard form text, unchanged
   "amended"    modified from standard form
   "additional" bespoke clause not in standard form
5. "references" — list of other clause numbers explicitly cited, e.g. ["15", "32"].

Return a single JSON object:
{{
  "number": {number},
  "title": "...",
  "agreed_text": "...",
  "sub_clauses": [{{"label": "(1)", "text": "..."}}],
  "status": "unamended|amended|additional",
  "references": []
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

        data["id"] = f"{section['prefix']}-{number}"
        data["section"] = section["title"]
        data["section_index"] = section["index"]
        data["page_range"] = [section["page_start"], section["page_end"]]
        data["confidence"] = 0.0

        return data

    except Exception as exc:
        logger.error("Extraction failed for %s-%s: %s", section["prefix"], number, exc)
        return {
            "id": f"{section['prefix']}-{number}",
            "number": number,
            "title": f"Clause {number}",
            "agreed_text": "",
            "sub_clauses": [],
            "status": "unamended",
            "references": [],
            "section": section["title"],
            "section_index": section["index"],
            "page_range": [section["page_start"], section["page_end"]],
            "confidence": 0.0,
            "error": str(exc),
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
