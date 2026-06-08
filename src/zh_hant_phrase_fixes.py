# -*- coding: utf-8 -*-
"""Post-OpenCC Taiwan phrase fixes shared with the Web UI."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

_PHRASE_FIXES_PATH = (
    Path(__file__).resolve().parents[1] / "shared" / "zh_hant_phrase_fixes.json"
)


@lru_cache(maxsize=1)
def get_zh_hant_phrase_fixes() -> Tuple[Tuple[str, str], ...]:
    """Load phrase fixes (longest source phrases first)."""
    try:
        raw = json.loads(_PHRASE_FIXES_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.warning("zh-Hant phrase fixes file missing (%s): %s", _PHRASE_FIXES_PATH, exc)
        return tuple()
    except json.JSONDecodeError as exc:
        logger.warning("zh-Hant phrase fixes JSON invalid: %s", exc)
        return tuple()

    pairs: List[Tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        source, target = str(item[0]), str(item[1])
        if source and source != target:
            pairs.append((source, target))
    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    return tuple(pairs)


def apply_zh_hant_phrase_fixes(text: str) -> str:
    """Apply domain-specific Taiwan wording fixes after OpenCC conversion."""
    if not text:
        return text
    out = text
    for source, target in get_zh_hant_phrase_fixes():
        if source in out:
            out = out.replace(source, target)
    return out
