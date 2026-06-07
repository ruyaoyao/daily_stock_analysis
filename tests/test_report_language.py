# -*- coding: utf-8 -*-
"""Unit tests for report language helpers."""

import unittest

from src.report_language import (
    _BIAS_STATUS_TRANSLATIONS,
    _CHIP_HEALTH_TRANSLATIONS,
    _CHIP_UNAVAILABLE_BY_LANGUAGE,
    _CONFIDENCE_LEVEL_TRANSLATIONS,
    _GENERIC_STOCK_NAME_BY_LANGUAGE,
    _NO_DATA_BY_LANGUAGE,
    _OPERATION_ADVICE_TRANSLATIONS,
    _PLACEHOLDER_BY_LANGUAGE,
    _REPORT_LABELS,
    _TREND_PREDICTION_TRANSLATIONS,
    _UNKNOWN_BY_LANGUAGE,
    get_bias_status_emoji,
    get_localized_stock_name,
    get_report_labels,
    get_sentiment_label,
    get_signal_level,
    infer_decision_type_from_advice,
    localize_operation_advice,
    localize_trend_prediction,
    localize_bias_status,
    normalize_report_language,
)


class ReportLanguageTestCase(unittest.TestCase):
    def test_get_signal_level_handles_compound_sell_advice(self) -> None:
        signal_text, emoji, signal_tag = get_signal_level("卖出/观望", 60, "zh")

        self.assertEqual(signal_text, "卖出")
        self.assertEqual(emoji, "🔴")
        self.assertEqual(signal_tag, "sell")

    def test_get_signal_level_handles_compound_buy_advice_in_english(self) -> None:
        signal_text, emoji, signal_tag = get_signal_level("Buy / Watch", 40, "en")

        self.assertEqual(signal_text, "Buy")
        self.assertEqual(emoji, "🟢")
        self.assertEqual(signal_tag, "buy")

    def test_get_localized_stock_name_replaces_placeholder_for_english(self) -> None:
        self.assertEqual(
            get_localized_stock_name("股票AAPL", "AAPL", "en"),
            "Unnamed Stock",
        )

    def test_get_sentiment_label_preserves_higher_band_thresholds(self) -> None:
        self.assertEqual(get_sentiment_label(80, "en"), "Very Bullish")
        self.assertEqual(get_sentiment_label(60, "en"), "Bullish")
        self.assertEqual(get_sentiment_label(40, "zh"), "中性")
        self.assertEqual(get_sentiment_label(20, "zh"), "悲观")

    def test_localize_trend_prediction_preserves_fine_grain_zh_states(self) -> None:
        self.assertEqual(localize_trend_prediction("多头排列", "zh"), "多头排列")
        self.assertEqual(localize_trend_prediction("弱势空头", "zh"), "弱势空头")

    def test_localize_trend_prediction_still_translates_english_input_for_zh(self) -> None:
        self.assertEqual(localize_trend_prediction("bullish", "zh"), "看多")
        self.assertEqual(localize_trend_prediction("very bearish", "zh"), "强烈看空")

    def test_bias_status_helpers_support_english_values(self) -> None:
        self.assertEqual(localize_bias_status("Safe", "en"), "Safe")
        self.assertEqual(localize_bias_status("警戒", "en"), "Caution")
        self.assertEqual(get_bias_status_emoji("Safe"), "✅")
        self.assertEqual(get_bias_status_emoji("Caution"), "⚠️")

    def test_infer_decision_type_from_advice_matches_chinese_phrases(self) -> None:
        self.assertEqual(infer_decision_type_from_advice("建议买入"), "buy")
        self.assertEqual(infer_decision_type_from_advice("建议持有"), "hold")
        self.assertEqual(infer_decision_type_from_advice("建议减仓"), "sell")
        self.assertEqual(infer_decision_type_from_advice("继续持有"), "hold")
        self.assertEqual(infer_decision_type_from_advice("建议洗盘观察"), "hold")
        self.assertEqual(infer_decision_type_from_advice("洗盘观察", default=""), "hold")
        self.assertEqual(infer_decision_type_from_advice("观察", default=""), "hold")
        self.assertEqual(infer_decision_type_from_advice("不建议买入"), "hold")
        self.assertEqual(
            infer_decision_type_from_advice("当前不跌破支撑位继续持有"),
            "hold",
        )
        self.assertEqual(
            infer_decision_type_from_advice("不破支撑后仍可持有"),
            "hold",
        )


class ZhHantNormalizeTestCase(unittest.TestCase):
    """Verify normalize_report_language resolves zh-Hant variants correctly."""

    def test_zh_hant_passthrough(self) -> None:
        # Raw "zh-Hant" → lowercased to "zh-hant" → alias → canonical "zh-Hant"
        self.assertEqual(normalize_report_language("zh-Hant"), "zh-Hant")

    def test_zh_tw_resolves_to_zh_hant(self) -> None:
        self.assertEqual(normalize_report_language("zh-TW"), "zh-Hant")

    def test_zh_cn_still_resolves_to_zh(self) -> None:
        self.assertEqual(normalize_report_language("zh-CN"), "zh")

    def test_tw_alias_resolves_to_zh_hant(self) -> None:
        self.assertEqual(normalize_report_language("tw"), "zh-Hant")

    def test_taiwan_alias_resolves_to_zh_hant(self) -> None:
        self.assertEqual(normalize_report_language("taiwan"), "zh-Hant")

    def test_zh_hk_resolves_to_zh_hant(self) -> None:
        self.assertEqual(normalize_report_language("zh-HK"), "zh-Hant")

    def test_zh_mo_resolves_to_zh_hant(self) -> None:
        self.assertEqual(normalize_report_language("zh-MO"), "zh-Hant")

    def test_traditional_alias_resolves_to_zh_hant(self) -> None:
        self.assertEqual(normalize_report_language("traditional"), "zh-Hant")

    def test_zh_hant_tw_resolves_to_zh_hant(self) -> None:
        self.assertEqual(normalize_report_language("zh-Hant-TW"), "zh-Hant")

    def test_existing_zh_en_unaffected(self) -> None:
        self.assertEqual(normalize_report_language("zh"), "zh")
        self.assertEqual(normalize_report_language("en"), "en")
        self.assertEqual(normalize_report_language("zh-CN"), "zh")
        self.assertEqual(normalize_report_language("chinese"), "zh")


class ZhHantLabelsTestCase(unittest.TestCase):
    """Verify _REPORT_LABELS["zh-Hant"] has parity with "zh" and correct values."""

    def test_zh_hant_has_same_keys_as_zh(self) -> None:
        self.assertEqual(
            set(_REPORT_LABELS["zh-Hant"]),
            set(_REPORT_LABELS["zh"]),
        )

    def test_get_report_labels_zh_hant_returns_correct_dict(self) -> None:
        labels = get_report_labels("zh-Hant")
        self.assertIsInstance(labels, dict)
        self.assertEqual(set(labels), set(_REPORT_LABELS["zh"]))

    def test_zh_hant_labels_contain_traditional_glyphs(self) -> None:
        labels = get_report_labels("zh-Hant")
        # 決策儀表板 contains Traditional glyphs absent in Simplified
        self.assertIn("決策儀表板", labels["dashboard_title"])
        # 籌碼 uses Traditional glyph (vs Simplified 筹码)
        self.assertIn("籌碼", labels["chip_label"])

    def test_zh_hant_labels_differ_from_zh_for_known_keys(self) -> None:
        zh_labels = get_report_labels("zh")
        hant_labels = get_report_labels("zh-Hant")
        # dashboard_title: 决策仪表盘 vs 決策儀表板
        self.assertNotEqual(zh_labels["dashboard_title"], hant_labels["dashboard_title"])
        # chip_label: 筹码 vs 籌碼
        self.assertNotEqual(zh_labels["chip_label"], hant_labels["chip_label"])


class ZhHantLocalizationTestCase(unittest.TestCase):
    """Verify localization functions return correct Traditional strings, no KeyError."""

    def test_localize_operation_advice_buy_zh_hant(self) -> None:
        result = localize_operation_advice("buy", "zh-Hant")
        self.assertTrue(result)  # non-empty
        self.assertEqual(result, "買進")

    def test_localize_operation_advice_strong_buy_zh_hant(self) -> None:
        self.assertEqual(localize_operation_advice("strong_buy", "zh-Hant"), "強烈買入")

    def test_localize_operation_advice_sell_zh_hant(self) -> None:
        self.assertEqual(localize_operation_advice("sell", "zh-Hant"), "賣出")

    def test_localize_operation_advice_reduce_zh_hant(self) -> None:
        self.assertEqual(localize_operation_advice("reduce", "zh-Hant"), "減碼")

    def test_localize_operation_advice_watch_zh_hant(self) -> None:
        self.assertEqual(localize_operation_advice("watch", "zh-Hant"), "觀望")

    def test_localize_trend_prediction_english_input_zh_hant(self) -> None:
        result = localize_trend_prediction("bullish", "zh-Hant")
        self.assertTrue(result)  # non-empty Traditional string
        self.assertEqual(result, "偏多")

    def test_localize_trend_prediction_chinese_input_preserved_zh_hant(self) -> None:
        # Chinese input should be returned as-is for zh-Hant (same guard as zh)
        self.assertEqual(localize_trend_prediction("多頭排列", "zh-Hant"), "多頭排列")
        self.assertEqual(localize_trend_prediction("盤整", "zh-Hant"), "盤整")

    def test_localize_trend_prediction_strong_bullish_zh_hant(self) -> None:
        self.assertEqual(localize_trend_prediction("strong bullish", "zh-Hant"), "強勢多頭")

    def test_get_sentiment_label_zh_hant_high_score(self) -> None:
        result = get_sentiment_label(85, "zh-Hant")
        self.assertTrue(result)  # non-empty
        self.assertEqual(result, "極度樂觀")

    def test_get_sentiment_label_zh_hant_all_bands(self) -> None:
        self.assertEqual(get_sentiment_label(80, "zh-Hant"), "極度樂觀")
        self.assertEqual(get_sentiment_label(60, "zh-Hant"), "樂觀")
        self.assertEqual(get_sentiment_label(40, "zh-Hant"), "中性")
        self.assertEqual(get_sentiment_label(20, "zh-Hant"), "悲觀")
        self.assertEqual(get_sentiment_label(10, "zh-Hant"), "極度悲觀")

    def test_get_sentiment_label_zh_unaffected(self) -> None:
        self.assertEqual(get_sentiment_label(80, "zh"), "极度乐观")
        self.assertEqual(get_sentiment_label(60, "zh"), "乐观")


class ZhHantParityTestCase(unittest.TestCase):
    """Verify all language-keyed dicts have zh-Hant alongside zh and en."""

    _TRANSLATION_DICTS = [
        _OPERATION_ADVICE_TRANSLATIONS,
        _TREND_PREDICTION_TRANSLATIONS,
        _CONFIDENCE_LEVEL_TRANSLATIONS,
        _CHIP_HEALTH_TRANSLATIONS,
        _BIAS_STATUS_TRANSLATIONS,
    ]
    _BY_LANGUAGE_DICTS = [
        _PLACEHOLDER_BY_LANGUAGE,
        _UNKNOWN_BY_LANGUAGE,
        _NO_DATA_BY_LANGUAGE,
        _CHIP_UNAVAILABLE_BY_LANGUAGE,
        _GENERIC_STOCK_NAME_BY_LANGUAGE,
    ]

    def test_translation_dicts_have_zh_hant(self) -> None:
        for d in self._TRANSLATION_DICTS:
            for canonical_key, lang_dict in d.items():
                self.assertIn(
                    "zh-Hant",
                    lang_dict,
                    msg=f"Missing 'zh-Hant' in {canonical_key}: {lang_dict}",
                )

    def test_by_language_dicts_have_zh_hant(self) -> None:
        for d in self._BY_LANGUAGE_DICTS:
            self.assertIn("zh-Hant", d, msg=f"Missing 'zh-Hant' in {d}")

    def test_report_labels_zh_hant_key_set_equals_zh(self) -> None:
        self.assertEqual(
            set(_REPORT_LABELS["zh-Hant"]),
            set(_REPORT_LABELS["zh"]),
        )

    def test_chip_unavailable_zh_hant_is_traditional(self) -> None:
        # 籌碼 is the Traditional form; Simplified uses 筹码
        self.assertIn("籌碼", _CHIP_UNAVAILABLE_BY_LANGUAGE["zh-Hant"])
        # Original zh entry unchanged
        self.assertIn("筹码", _CHIP_UNAVAILABLE_BY_LANGUAGE["zh"])


if __name__ == "__main__":
    unittest.main()
