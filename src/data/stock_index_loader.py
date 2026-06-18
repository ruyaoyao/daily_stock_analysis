# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import RLock
from typing import Dict, Iterable, Optional

from src.data.stock_mapping import is_meaningful_stock_name
from src.services.stock_index_remote_service import (
    get_remote_stock_index_cache_path,
    is_valid_remote_stock_index_file,
    validate_stock_index_payload,
)

logger = logging.getLogger(__name__)

_STOCK_INDEX_FILENAME = "stocks.index.json"
_STOCK_INDEX_CACHE: Dict[str, str] | None = None
_REMOTE_INDEX_VALIDITY_CACHE: tuple[Path, float, int, bool] | None = None
_SERVED_STOCK_INDEX_CACHE: tuple[Path, float, int, bytes] | None = None
_STOCK_INDEX_CACHE_LOCK = RLock()


def get_stock_index_candidate_paths() -> tuple[Path, ...]:
    """Return the supported locations for the generated stock index."""
    repo_root = Path(__file__).resolve().parents[2]
    return (
        get_remote_stock_index_cache_path(),
        repo_root / "apps" / "dsa-web" / "public" / _STOCK_INDEX_FILENAME,
        repo_root / "static" / _STOCK_INDEX_FILENAME,
    )


def _same_path(left: Path, right: Path) -> bool:
    return left == right or left.resolve() == right.resolve()


def _add_lookup_key(keys: set[str], value: str) -> None:
    candidate = str(value or "").strip()
    if not candidate:
        return
    keys.add(candidate)
    keys.add(candidate.upper())


def _build_lookup_keys(canonical_code: str, display_code: str) -> Iterable[str]:
    keys: set[str] = set()
    _add_lookup_key(keys, canonical_code)
    _add_lookup_key(keys, display_code)

    canonical_upper = str(canonical_code or "").strip().upper()
    display_upper = str(display_code or "").strip().upper()

    if "." in canonical_upper:
        base, suffix = canonical_upper.rsplit(".", 1)
        if suffix in {"SH", "SZ", "SS", "BJ"} and base.isdigit():
            _add_lookup_key(keys, base)
        elif suffix == "HK" and base.isdigit() and 1 <= len(base) <= 5:
            digits = base.zfill(5)
            _add_lookup_key(keys, digits)
            _add_lookup_key(keys, f"HK{digits}")

    for candidate in (canonical_upper, display_upper):
        if candidate.startswith("HK"):
            digits = candidate[2:]
            if digits.isdigit() and 1 <= len(digits) <= 5:
                digits = digits.zfill(5)
                _add_lookup_key(keys, digits)
                _add_lookup_key(keys, f"HK{digits}")

    return keys


def _load_stock_index_payload(index_path: Path) -> list:
    with index_path.open("r", encoding="utf-8") as fh:
        raw_items = json.load(fh)

    if not isinstance(raw_items, list):
        raise ValueError(
            f"Unexpected {_STOCK_INDEX_FILENAME} payload type: {type(raw_items).__name__}"
        )
    return raw_items


def _build_stock_name_map(raw_items: list) -> Dict[str, str]:
    stock_name_map: Dict[str, str] = {}
    for item in raw_items:
        if not isinstance(item, list) or len(item) < 3:
            continue

        canonical_code, display_code, name_zh = item[0], item[1], item[2]
        if not is_meaningful_stock_name(name_zh, str(display_code or canonical_code or "")):
            continue

        for key in _build_lookup_keys(str(canonical_code or ""), str(display_code or "")):
            stock_name_map[key] = str(name_zh).strip()

    return stock_name_map


def _load_stock_index_file(index_path: Path) -> Dict[str, str]:
    return _build_stock_name_map(_load_stock_index_payload(index_path))


def _load_remote_stock_index_file(index_path: Path) -> Dict[str, str]:
    raw_items = _load_stock_index_payload(index_path)
    validate_stock_index_payload(raw_items)
    return _build_stock_name_map(raw_items)


def _bundled_stock_index_paths() -> tuple[Path, ...]:
    """Local bundled index candidates (everything except the remote cache)."""
    remote = get_remote_stock_index_cache_path()
    return tuple(p for p in get_stock_index_candidate_paths() if not _same_path(p, remote))


def _supplement_with_bundled_entries(active_map: Dict[str, str]) -> Dict[str, str]:
    """Union bundled-index entries that the active (remote) map is missing.

    The remote index is fetched from a generic source that may not carry markets
    this fork ships locally (e.g. Taiwan TW/TWO). Without this, a remote refresh
    would silently drop those stocks. Active entries win — only keys absent from
    ``active_map`` are added — so the remote stays authoritative and fresh for the
    markets it does cover, while local-only markets are always preserved.
    """
    for path in _bundled_stock_index_paths():
        try:
            bundled = _load_stock_index_file(path)
        except (OSError, TypeError, ValueError) as exc:
            logger.debug("[股票名称] 读取内建索引失败 %s: %s", path, exc)
            continue
        if not bundled:
            continue
        added = 0
        for key, name in bundled.items():
            if key not in active_map:
                active_map[key] = name
                added += 1
        if added:
            logger.info(
                "[股票名称] 远程索引缺失本地市场，已从内建索引 %s 补入 %d 个键（避免台股等被覆盖）",
                path, added,
            )
        return active_map  # first usable bundled file already carries all local markets
    return active_map


def _stock_index_item_key(item: object) -> Optional[str]:
    """Return the canonical-code dedupe key for a wire payload item."""
    if not isinstance(item, list) or not item:
        return None
    canonical = str(item[0] or "").strip().upper()
    return canonical or None


def supplement_payload_with_bundled_markets(remote_items: list) -> list:
    """Union bundled-index entries missing from the remote wire payload.

    Mirrors :func:`_supplement_with_bundled_entries` (which protects backend name
    lookup) but operates on the full ``stocks.index.json`` payload, so the
    *served* autocomplete index keeps fork-local markets (Taiwan TW/TWO) that the
    upstream remote index omits. Remote entries stay authoritative; only canonical
    codes absent from the remote payload are appended. A new list is returned —
    the inputs are never mutated.
    """
    if not isinstance(remote_items, list):
        return remote_items

    remote_keys = {
        key for key in (_stock_index_item_key(item) for item in remote_items) if key
    }
    for path in _bundled_stock_index_paths():
        try:
            bundled = _load_stock_index_payload(path)
        except (OSError, TypeError, ValueError) as exc:
            logger.debug("[股票名称] 读取内建索引失败 %s: %s", path, exc)
            continue
        if not isinstance(bundled, list) or not bundled:
            continue
        supplemental = [
            item
            for item in bundled
            if (key := _stock_index_item_key(item)) is not None and key not in remote_keys
        ]
        if supplemental:
            logger.info(
                "[股票名称] 远程索引缺失本地市场，下发索引已补入 %d 条（避免台股等被覆盖）",
                len(supplemental),
            )
        # first usable bundled file already carries all local markets
        return remote_items + supplemental
    return remote_items


def get_served_stock_index_bytes(index_path: Path) -> bytes:
    """Return the JSON bytes to serve for ``index_path``.

    Bundled indexes ship fork-local markets, so they are served verbatim. The
    remote cache may omit them (Taiwan TW/TWO); in that case the payload is
    unioned with bundled entries before serving so the autocomplete never drops
    those stocks. Cached by ``(path, mtime, size)`` so the merge only runs when
    the underlying file changes. Falls back to the raw bytes if the payload
    cannot be parsed.
    """
    global _SERVED_STOCK_INDEX_CACHE

    raw = index_path.read_bytes()
    remote_cache_path = get_remote_stock_index_cache_path()
    if not _same_path(index_path, remote_cache_path):
        return raw

    signature = _get_stock_index_signature(index_path)
    with _STOCK_INDEX_CACHE_LOCK:
        cached = _SERVED_STOCK_INDEX_CACHE
        if (
            cached is not None
            and signature is not None
            and cached[0] == index_path
            and (cached[1], cached[2]) == signature
        ):
            return cached[3]

        try:
            payload = json.loads(raw.decode("utf-8"))
            merged = supplement_payload_with_bundled_markets(payload)
            content = json.dumps(
                merged, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
        except (ValueError, TypeError) as exc:
            logger.debug("[股票名称] 下发索引补全失败，回退原始内容: %s", exc)
            return raw

        if signature is not None:
            _SERVED_STOCK_INDEX_CACHE = (index_path, signature[0], signature[1], content)
        return content


def _get_stock_index_signature(index_path: Path) -> tuple[float, int] | None:
    try:
        stat_result = index_path.stat()
    except OSError as exc:
        logger.debug("[股票名称] 读取股票索引元数据失败 %s: %s", index_path, exc)
        return None
    if not index_path.is_file():
        return None
    return stat_result.st_mtime, stat_result.st_size


def _get_fresh_stock_index_candidates(
    candidate_paths: Iterable[Path],
    remote_cache_path: Path,
) -> tuple[Path, ...]:
    paths = tuple(candidate_paths)
    candidates: list[tuple[tuple[float, int], Path]] = []

    for position, candidate_path in enumerate(paths):
        signature = _get_stock_index_signature(candidate_path)
        if signature is None:
            continue

        mtime, _size = signature
        tie_breaker = 0 if _same_path(candidate_path, remote_cache_path) else len(paths) - position
        candidates.append(((mtime, tie_breaker), candidate_path))

    return tuple(path for _sort_key, path in sorted(candidates, reverse=True))


def _is_remote_stock_index_cache_usable(
    index_path: Path,
    remote_cache_path: Path,
    signature: tuple[float, int],
) -> bool:
    global _REMOTE_INDEX_VALIDITY_CACHE

    if not _same_path(index_path, remote_cache_path):
        return True

    mtime, size = signature
    cached = _REMOTE_INDEX_VALIDITY_CACHE
    if cached is not None and cached[:3] == (index_path, mtime, size):
        return cached[3]

    is_valid = is_valid_remote_stock_index_file(index_path)
    _REMOTE_INDEX_VALIDITY_CACHE = (index_path, mtime, size, is_valid)
    return is_valid


def find_existing_stock_index_path(
    candidate_paths: Optional[Iterable[Path]] = None,
    *,
    remote_cache_path: Optional[Path] = None,
) -> Path | None:
    """Return the newest usable stock index across remote and bundled candidates."""
    paths = tuple(candidate_paths) if candidate_paths is not None else get_stock_index_candidate_paths()
    remote_path = remote_cache_path or get_remote_stock_index_cache_path()

    for candidate_path in _get_fresh_stock_index_candidates(paths, remote_path):
        signature = _get_stock_index_signature(candidate_path)
        if signature is None:
            continue
        if not _is_remote_stock_index_cache_usable(candidate_path, remote_path, signature):
            continue

        return candidate_path

    return None


def get_stock_name_index_map() -> Dict[str, str]:
    """Lazily load and cache the generated stock-name index."""
    global _STOCK_INDEX_CACHE

    if _STOCK_INDEX_CACHE is not None:
        return _STOCK_INDEX_CACHE

    with _STOCK_INDEX_CACHE_LOCK:
        if _STOCK_INDEX_CACHE is not None:
            return _STOCK_INDEX_CACHE

        remote_path = get_remote_stock_index_cache_path()
        for index_path in _get_fresh_stock_index_candidates(get_stock_index_candidate_paths(), remote_path):
            try:
                if _same_path(index_path, remote_path):
                    # Remote (upstream) index may lack fork-local markets (TW/TWO);
                    # union bundled entries so a remote refresh never drops them.
                    _STOCK_INDEX_CACHE = _supplement_with_bundled_entries(
                        _load_remote_stock_index_file(index_path)
                    )
                else:
                    _STOCK_INDEX_CACHE = _load_stock_index_file(index_path)
                logger.debug(
                    "[股票名称] 已加载前端股票索引映射: %s (%d 条)",
                    index_path,
                    len(_STOCK_INDEX_CACHE),
                )
                return _STOCK_INDEX_CACHE
            except (OSError, TypeError, ValueError) as exc:
                logger.debug("[股票名称] 读取股票索引失败 %s: %s", index_path, exc)

        _STOCK_INDEX_CACHE = {}
        return _STOCK_INDEX_CACHE


def get_index_stock_name(stock_code: str) -> str | None:
    """Resolve a stock name from the generated frontend stock index."""
    code = str(stock_code or "").strip()
    if not code:
        return None

    stock_name_map = get_stock_name_index_map()
    for key in _build_lookup_keys(code, code):
        name = stock_name_map.get(key)
        if is_meaningful_stock_name(name, code):
            return name

    return None


def clear_stock_index_cache() -> None:
    """Clear the in-process stock index lookup cache."""
    global _REMOTE_INDEX_VALIDITY_CACHE, _STOCK_INDEX_CACHE, _SERVED_STOCK_INDEX_CACHE
    with _STOCK_INDEX_CACHE_LOCK:
        _STOCK_INDEX_CACHE = None
        _REMOTE_INDEX_VALIDITY_CACHE = None
        _SERVED_STOCK_INDEX_CACHE = None


def _clear_stock_index_cache_for_tests() -> None:
    clear_stock_index_cache()
