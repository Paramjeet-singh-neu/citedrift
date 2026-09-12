"""Assemble AI Overview answer text. Join rule is frozen — do not change."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

log = logging.getLogger("citedrift.parse")

KNOWN_BLOCK_TYPES = frozenset({"paragraph", "heading", "list"})


def assemble_answer(text_blocks: list[Any] | None) -> str:
    if not text_blocks:
        return ""
    parts: list[str] = []
    for block in text_blocks:
        if not isinstance(block, dict):
            log.warning("unrecognized text_block type: %s", type(block).__name__)
            continue
        btype = block.get("type")
        if btype in ("paragraph", "heading"):
            snippet = block.get("snippet")
            if isinstance(snippet, str):
                parts.append(snippet)
        elif btype == "list":
            items = block.get("list") or []
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and isinstance(item.get("snippet"), str):
                        parts.append(item["snippet"])
        else:
            log.warning("unrecognized text_block type: %s", btype)
    return "\n".join(parts).strip()


def answer_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
