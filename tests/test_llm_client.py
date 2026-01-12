import unittest

from one_person_dnd.config import LLMConfig
from one_person_dnd.llm.client import OpenAICompatClient


class TestOpenAICompatClient(unittest.TestCase):
    def test_endpoint_appends_chat_completions(self) -> None:
        cfg = LLMConfig(base_url="http://localhost:8000/v1", api_key="", model="m")
        c = OpenAICompatClient(cfg)
        self.assertEqual(c._endpoint(), "http://localhost:8000/v1/chat/completions")

    def test_endpoint_does_not_double_append(self) -> None:
        cfg = LLMConfig(base_url="http://localhost:8000/v1/chat/completions", api_key="", model="m")
        c = OpenAICompatClient(cfg)
        self.assertEqual(c._endpoint(), "http://localhost:8000/v1/chat/completions")

    def test_headers_without_api_key(self) -> None:
        cfg = LLMConfig(base_url="http://localhost:8000/v1", api_key="", model="m")
        c = OpenAICompatClient(cfg)
        headers = c._headers()
        self.assertNotIn("Authorization", headers)
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_headers_with_api_key(self) -> None:
        cfg = LLMConfig(base_url="http://localhost:8000/v1", api_key="k", model="m")
        c = OpenAICompatClient(cfg)
        headers = c._headers()
        self.assertEqual(headers["Authorization"], "Bearer k")

