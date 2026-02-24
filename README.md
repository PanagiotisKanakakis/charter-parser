# Charter Party Clause Extractor

Extracts legal clauses from voyage charter party PDFs. Handles strikethrough detection, multi-section documents, and two-column layouts.

## Setup

```bash
make install
cp .env.example .env  # add your ANTHROPIC_API_KEY
```

## Usage

```bash
make run

# or directly
uv run python -m charter_parser.main voyage-charter-example.pdf
uv run python -m charter_parser.main charter.pdf --output output/result.json
uv run python -m charter_parser.main charter.pdf --log-level DEBUG
```

## Output

Writes a JSON array to `output/clauses.json`:

```json
[
  {"id": "1", "title": "Condition Of Vessel", "text": "Owners shall exercise due diligence..."},
  {"id": "2", "title": "Cargo", "text": "Whilst loading, carrying and discharging..."}
]
```

Struck-through clauses (deleted from the standard form) are excluded.

## Pipeline

```
PDF
 └─ loader       pdfplumber strikethrough + Docling layout extraction
 └─ sectioner    splits into sections by detecting numbering restarts
 └─ enumerator   Haiku lists clause numbers per section
 └─ extractor    Sonnet extracts each clause (concurrent per section)
 └─ assembler    sorts + outputs JSON
```

### Strikethrough

Charter parties mark deleted clauses by drawing a line through the text. Most PDF parsers miss this because it's a graphic overlay, not a font property — Docling doesn't pick it up either.

We use pdfplumber to get the raw geometry: every rectangle and every character with its bounding box. A strikethrough is just a thin horizontal rect that sits in the middle of a line of text. The loader finds these rects, matches them against character positions, and drops any element where more than half the text is crossed out.

### Two-pass extraction

Sending the full section to an LLM with "extract all clauses" doesn't work well in practice. A section can have 40+ clauses across 60k chars of text. The LLM tends to silently skip some, and if the JSON is malformed you lose everything.

Instead, we split it into two passes:

1. **Enumerate** (Haiku) — just returns clause numbers as a JSON array, like `[1, 2, 3, ..., 43]`. Cheap, fast, and easy to validate (we check they're monotonically increasing). This gives us the "table of contents" for each section.

2. **Extract** (Sonnet) — one call per clause number, all running concurrently within each section via `asyncio.gather`. Each call gets the full section text but is told to extract only clause N. If one fails, the rest still succeed.

This way Python controls the loop. The LLM can't skip clauses or reorder them.

### Section detection

Charter parties often have multiple sections with independent clause numbering that restarts at 1. The sectioner detects these by looking for numbering restarts — when clause numbers jump from something high back to 1 or 2, and there's a title header nearby, that's a section boundary.

### Margin notes

Some sections use a two-column layout with clause titles in a narrow left sidebar. These margin notes shouldn't be included in the text sent to the LLM. We detect them using bounding box geometry: per page, find the main content column (the x-position bucket with the most text), then tag anything whose right edge doesn't reach it.

## Project Structure

```
charter_parser/
├── main.py               entry point + pipeline wiring
├── state.py              shared TypedDicts
└── pipeline/
    ├── loader.py          strikethrough detection + Docling conversion
    ├── sectioner.py       section boundary detection
    ├── enumerator.py      pass 1: clause number listing
    ├── extractor.py       pass 2: clause extraction (async)
    └── assembler.py       sort + format final output
```
