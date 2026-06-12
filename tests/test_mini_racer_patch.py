# -*- coding: utf-8 -*-
"""Tests for py_mini_racer thread-safety patch."""

from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock, patch

from src.patches.mini_racer_patch import apply_mini_racer_thread_patch


class TestMiniRacerPatch(unittest.TestCase):
    def setUp(self) -> None:
        import src.patches.mini_racer_patch as patch_module

        patch_module._PATCH_APPLIED = False

    def test_apply_patch_is_idempotent(self) -> None:
        fake_module = MagicMock()
        fake_module.MiniRacer = type(
            "MiniRacer",
            (),
            {
                "_dsa_thread_safe_patch": False,
                "__init__": lambda self, *args, **kwargs: None,
                "eval": lambda self, code: code,
            },
        )

        with patch.dict("sys.modules", {"py_mini_racer": fake_module}):
            import src.patches.mini_racer_patch as patch_module

            patch_module._PATCH_APPLIED = False
            self.assertTrue(apply_mini_racer_thread_patch())
            first_cls = fake_module.MiniRacer
            self.assertTrue(apply_mini_racer_thread_patch())
            self.assertIs(fake_module.MiniRacer, first_cls)

    def test_concurrent_eval_runs_without_error(self) -> None:
        try:
            import py_mini_racer
        except ImportError:
            self.skipTest("py_mini_racer is not installed")

        apply_mini_racer_thread_patch()
        errors: list[BaseException] = []

        def worker(value: int) -> None:
            try:
                ctx = py_mini_racer.MiniRacer()
                result = ctx.eval(f"1 + {value}")
                if int(result) != value + 1:
                    raise AssertionError(f"unexpected eval result: {result!r}")
            except BaseException as exc:  # pragma: no cover - surfaced via errors list
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            if thread.is_alive():
                self.fail("mini_racer worker thread did not finish")

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
