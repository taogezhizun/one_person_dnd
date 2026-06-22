import unittest

from one_person_dnd.config import LLMConfig
from one_person_dnd.llm.providers import (
    apply_provider_defaults,
    get_provider_preset,
    list_provider_presets,
)


class TestLLMProviderPresets(unittest.TestCase):
    def test_deepseek_preset_exists(self) -> None:
        preset = get_provider_preset("deepseek")
        self.assertEqual(preset.id, "deepseek")
        self.assertEqual(preset.provider, "deepseek")
        self.assertEqual(preset.base_url, "https://api.deepseek.com/v1")
        self.assertEqual(preset.default_model, "deepseek-chat")
        self.assertFalse(preset.allows_empty_api_key)

    def test_openai_compat_custom_preset_exists(self) -> None:
        ids = [p.id for p in list_provider_presets()]
        self.assertIn("openai_compat", ids)
        self.assertIn("deepseek", ids)

    def test_apply_provider_defaults_fills_missing_values(self) -> None:
        cfg = LLMConfig(provider="deepseek", base_url="", api_key="k", model="")
        out = apply_provider_defaults(cfg)
        self.assertEqual(out.provider, "deepseek")
        self.assertEqual(out.base_url, "https://api.deepseek.com/v1")
        self.assertEqual(out.model, "deepseek-chat")
        self.assertEqual(out.api_key, "k")

    def test_apply_provider_defaults_preserves_explicit_values(self) -> None:
        cfg = LLMConfig(
            provider="deepseek",
            base_url="https://proxy.example/v1",
            api_key="k",
            model="deepseek-reasoner",
        )
        out = apply_provider_defaults(cfg)
        self.assertEqual(out.base_url, "https://proxy.example/v1")
        self.assertEqual(out.model, "deepseek-reasoner")

    def test_provider_helpers_are_exported_from_llm_package(self) -> None:
        from one_person_dnd.llm import get_provider_preset as exported_get_provider_preset
        from one_person_dnd.llm import list_provider_presets as exported_list_provider_presets

        self.assertEqual(exported_get_provider_preset("deepseek").default_model, "deepseek-chat")
        self.assertIn("deepseek", [p.id for p in exported_list_provider_presets()])
