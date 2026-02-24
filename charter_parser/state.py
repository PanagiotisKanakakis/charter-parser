"""
Shared TypedDicts for the extraction pipeline.
"""

from typing import TypedDict


class DocumentElement(TypedDict):
    label: str       # SECTION_HEADER, TEXT, TABLE, LIST_ITEM, ...
    text: str
    page: int        # 1-indexed
    level: int       # heading level if applicable
    is_margin_note: bool  # sidebar annotation in two-column layouts


class SectionData(TypedDict):
    title: str
    prefix: str
    index: int
    elements: list[DocumentElement]
    text: str
    page_start: int
    page_end: int
