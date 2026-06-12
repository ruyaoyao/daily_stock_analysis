"""Serialize py_mini_racer usage for concurrent analysis workers.

akshare creates ``py_mini_racer.MiniRacer`` instances from multiple threads when
DSA runs stock analysis concurrently (TaskQueue / ThreadPoolExecutor). On macOS
with Python 3.12+, concurrent V8 pool initialization can crash the process with:

    [FATAL:address_pool_manager.cc(67)] Check failed: !pool->IsInitialized().

This patch replaces MiniRacer with a composition-based proxy that serializes
instance creation and JS execution behind a process-wide lock.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_PATCH_APPLIED = False
_MINI_RACER_LOCK = threading.RLock()
_LOCKED_METHODS = frozenset(
    {
        "eval",
        "eval_cancelable",
        "call",
        "execute",
        "wrap_py_function",
        "close",
    }
)


def apply_mini_racer_thread_patch() -> bool:
    """Patch py_mini_racer.MiniRacer to be thread-safe for akshare callers."""
    global _PATCH_APPLIED

    try:
        import py_mini_racer
    except ImportError:
        logger.debug("py_mini_racer not installed; thread patch skipped")
        return False

    if getattr(py_mini_racer.MiniRacer, "_dsa_thread_safe_patch", False):
        _PATCH_APPLIED = True
        return True

    if _PATCH_APPLIED:
        # A previous patch attempt may have failed; retry on the live module.
        _PATCH_APPLIED = False

    original_cls = py_mini_racer.MiniRacer

    class ThreadSafeMiniRacer:
        _dsa_thread_safe_patch = True

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            with _MINI_RACER_LOCK:
                self._inner = original_cls(*args, **kwargs)

        def __getattr__(self, name: str) -> Any:
            attr = getattr(self._inner, name)
            if name not in _LOCKED_METHODS or not callable(attr):
                return attr

            def locked_method(*args: Any, **kwargs: Any) -> Any:
                with _MINI_RACER_LOCK:
                    return attr(*args, **kwargs)

            return locked_method

        def __del__(self) -> None:
            inner = getattr(self, "_inner", None)
            if inner is None:
                return
            try:
                with _MINI_RACER_LOCK:
                    inner.close()
            except Exception:
                logger.debug("MiniRacer close during __del__ failed", exc_info=True)

    py_mini_racer.MiniRacer = ThreadSafeMiniRacer
    _PATCH_APPLIED = True
    logger.debug("Applied py_mini_racer thread-safety patch")
    return True
