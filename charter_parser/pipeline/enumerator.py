"""
Pass 1: list clause numbers per section using Haiku.

Returns a JSON array of ints. Validates they're monotonically increasing.
Retries up to 3 times on failure.
"""

import json
import logging
import re

import anthropic

from charter_parser.state import SectionData

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3

ENUMERATE_PROMPT = """\
You are reading a section of a maritime charter party document.

Your ONLY task: list every top-level clause NUMBER that appears in this text,
in the order they appear.

Rules:
- Top-level clauses are numbered with integers: 1, 2, 3 ...
- Do NOT list sub-clause labels: (a), (b), (1), (i) etc.
- Do NOT invent numbers that are not present in the text.
- Return ONLY a JSON array of integers, e.g. [1, 2, 3, 4, 5]

DOCUMENT SECTION:
---
{text}
---

Return ONLY the JSON array. Nothing else."""


def _call_llm(client: anthropic.Anthropic, section: SectionData) -> list[int]:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": ENUMERATE_PROMPT.format(text=section["text"])
        }]
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    return json.loads(raw)


def _validate(numbers: list[int]) -> str | None:
    if not numbers:
        return "Empty list"
    if not all(isinstance(n, int) for n in numbers):
        return f"Non-integer values: {numbers}"
    if numbers != sorted(set(numbers)):
        return f"Not monotonically increasing or has duplicates: {numbers}"
    return None


def enumerate_clauses(state: dict) -> dict:
    client = anthropic.Anthropic()
    sections = state["sections"]
    attempts = state.get("enumeration_attempts", 0) + 1

    clause_index: dict[str, list[int]] = {}
    errors: list[str] = []

    for section in sections:
        logger.info("Enumerating: %r", section["title"])
        try:
            numbers = _call_llm(client, section)
            error = _validate(numbers)
            if error:
                msg = f"Enumeration invalid for {section['title']!r}: {error}"
                logger.warning(msg)
                errors.append(msg)
                clause_index[section["title"]] = []
            else:
                logger.info("  Found %d clauses: %s", len(numbers), numbers)
                clause_index[section["title"]] = numbers
        except Exception as exc:
            msg = f"Enumeration failed for {section['title']!r}: {exc}"
            logger.error(msg)
            errors.append(msg)
            clause_index[section["title"]] = []

    return {
        "clause_index": clause_index,
        "enumeration_attempts": attempts,
        "errors": errors,
    }


def should_retry(state: dict) -> bool:
    attempts = state.get("enumeration_attempts", 0)
    index = state.get("clause_index", {})
    has_empty = any(len(v) == 0 for v in index.values())

    if has_empty and attempts < MAX_ATTEMPTS:
        logger.warning("Retrying enumeration (attempt %d/%d)", attempts, MAX_ATTEMPTS)
        return True

    if has_empty:
        logger.error("Enumeration failed after %d attempts, proceeding with partial results", MAX_ATTEMPTS)

    return False
