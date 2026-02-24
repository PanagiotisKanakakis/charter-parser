"""CLI entry point for the charter party clause extractor."""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from charter_parser.pipeline.loader import load_document
from charter_parser.pipeline.sectioner import discover_sections
from charter_parser.pipeline.enumerator import enumerate_clauses, should_retry
from charter_parser.pipeline.extractor import extract_clauses
from charter_parser.pipeline.assembler import assemble

logger = logging.getLogger(__name__)


def run_pipeline(pdf_path: str) -> dict:
    """Run the full extraction pipeline, return final state."""
    state: dict = {"pdf_path": pdf_path, "enumeration_attempts": 0, "raw_clauses": [], "errors": []}

    state.update(load_document(state))
    state.update(discover_sections(state))

    # Enumerate with retry
    while True:
        state.update(enumerate_clauses(state))
        if not should_retry(state):
            break

    state.update(extract_clauses(state))
    state.update(assemble(state))

    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract clauses from a charter party PDF.")
    parser.add_argument("pdf_path", help="Path to the charter party PDF")
    parser.add_argument("--output", "-o", default="output/clauses.json")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(name)s: %(message)s")

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        logger.error("File not found: %s", pdf_path)
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.time()
    logger.info("Extracting clauses from %s", pdf_path)

    try:
        state = run_pipeline(str(pdf_path))
    except Exception:
        logger.exception("Pipeline failed")
        return 1

    clauses = state.get("clauses", [])

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(clauses, fh, indent=2, ensure_ascii=False)

    logger.info("Done: %d clauses -> %s (%.1fs)",
                len(clauses), output_path, time.time() - start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
