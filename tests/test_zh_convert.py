# -*- coding: utf-8 -*-
"""src/zh_convert.to_report_script 离线单测（不依赖 opencc 实际安装）。"""

import importlib

import src.zh_convert as zc


def _reset_converter_cache():
    zc._converter = None
    zc._converter_initialized = False


def test_non_zh_hant_returns_original():
    # zh（简体）与 en 一律原样返回，不触发转换器
    assert zc.to_report_script("决策仪表盘", "zh") == "决策仪表盘"
    assert zc.to_report_script("Decision Dashboard", "en") == "Decision Dashboard"
    # zh-CN 归一化为 zh，也不转换
    assert zc.to_report_script("决策仪表盘", "zh-CN") == "决策仪表盘"


def test_none_and_non_string_passthrough():
    assert zc.to_report_script(None, "zh-Hant") is None
    assert zc.to_report_script("", "zh-Hant") == ""
    assert zc.to_report_script(123, "zh-Hant") == 123


def test_zh_hant_graceful_when_converter_unavailable(monkeypatch):
    # 模拟 opencc 不可用：返回原文（不抛异常）
    _reset_converter_cache()
    monkeypatch.setattr(zc, "_get_converter", lambda: None)
    assert zc.to_report_script("决策仪表盘", "zh-Hant") == "决策仪表盘"
    assert zc.to_report_script("决策仪表盘", "zh-TW") == "决策仪表盘"  # 别名归一化为 zh-Hant


def test_zh_hant_uses_converter_when_available(monkeypatch):
    # 注入假的转换器，验证 zh-Hant 会调用 convert
    _reset_converter_cache()

    class _FakeConverter:
        def convert(self, text: str) -> str:
            return text.replace("决策仪表盘", "決策儀表板")

    monkeypatch.setattr(zc, "_get_converter", lambda: _FakeConverter())
    assert zc.to_report_script("决策仪表盘", "zh-Hant") == "決策儀表板"


def test_converter_failure_returns_original(monkeypatch):
    _reset_converter_cache()

    class _BoomConverter:
        def convert(self, text: str) -> str:
            raise RuntimeError("boom")

    monkeypatch.setattr(zc, "_get_converter", lambda: _BoomConverter())
    assert zc.to_report_script("决策仪表盘", "zh-Hant") == "决策仪表盘"



def test_phrase_fixes_after_opencc(monkeypatch):
    _reset_converter_cache()

    class _FakeConverter:
        def convert(self, text: str) -> str:
            return text.replace("代码", "程式碼").replace("支持位", "支援位")

    monkeypatch.setattr(zc, "_get_converter", lambda: _FakeConverter())
    result = zc.to_report_script("股票代码/支持位/后台/配置", "zh-Hant")
    assert "股票代碼" in result
    assert "支撐位" in result
    assert "後台" in result
    assert "設定" in result
    assert "程式碼" not in result
    assert "支援位" not in result


def test_phrase_fixes_module():
    from src.zh_hant_phrase_fixes import apply_zh_hant_phrase_fixes

    assert apply_zh_hant_phrase_fixes("止损/止損/用户/数据") == "停損/停損/使用者/資料"

def test_module_imports_clean():
    importlib.reload(zc)
