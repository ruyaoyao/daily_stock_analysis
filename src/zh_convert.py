# -*- coding: utf-8 -*-
"""
简体 -> 繁体（台湾用语）报告输出转换。

当 report_language 解析为 ``zh-Hant`` 时，在报告输出边界统一将 Markdown
文本（含 LLM 生成正文、Python 组装的固定文案与模板）转换为台湾繁体中文。

设计要点：
- 可选依赖 ``opencc``（s2twp 配置：简体 -> 台湾繁体并套用台湾惯用词）。
  未安装时优雅降级：返回原文（简体），仅记录一次 warning，不抛异常、不中断流程。
- 仅在 zh-Hant 时转换；zh（简体）与 en 一律原样返回。English 文本即使被转换
  也不受影响（s2twp 不改动非中文字符）。
"""

import logging
from typing import Optional

from src.report_language import normalize_report_language

logger = logging.getLogger(__name__)

_converter = None
_converter_initialized = False


def _get_converter():
    """懒加载并缓存 OpenCC 转换器；不可用时返回 None（只告警一次）。"""
    global _converter, _converter_initialized
    if _converter_initialized:
        return _converter
    _converter_initialized = True
    try:
        from opencc import OpenCC

        _converter = OpenCC("s2twp")
    except Exception as exc:  # ImportError 或配置缺失等
        logger.warning(
            "opencc 不可用，zh-Hant 报告将保持原文（不转换为繁体）：%s。"
            "如需繁体输出请安装 opencc。",
            exc,
        )
        _converter = None
    return _converter


def to_report_script(text: Optional[str], language: Optional[str]) -> Optional[str]:
    """按目标语言转换报告文本。

    Args:
        text: 报告/通知文本（Markdown）。None 或非字符串原样返回。
        language: 目标报告语言（任意可被 normalize_report_language 识别的值）。

    Returns:
        当 language 解析为 ``zh-Hant`` 且 opencc 可用时返回台湾繁体；否则原样返回。
    """
    if not text or not isinstance(text, str):
        return text
    if normalize_report_language(language) != "zh-Hant":
        return text
    converter = _get_converter()
    if converter is None:
        return text
    try:
        return converter.convert(text)
    except Exception as exc:
        logger.warning("zh-Hant 繁体转换失败，返回原文：%s", exc)
        return text
