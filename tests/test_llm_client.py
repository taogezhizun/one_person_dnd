import unittest

from one_person_dnd.config import LLMConfig
from one_person_dnd.llm.client import (
    OpenAICompatClient,
    create_llm_client,
    redact_llm_error_body,
)


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

    def test_deepseek_uses_openai_compatible_endpoint(self) -> None:
        cfg = LLMConfig(provider="deepseek", base_url="", api_key="k", model="")
        c = create_llm_client(cfg)
        self.assertIsInstance(c, OpenAICompatClient)
        self.assertEqual(c._endpoint(), "https://api.deepseek.com/v1/chat/completions")
        self.assertEqual(c._headers()["Authorization"], "Bearer k")


class TestRedactLLMErrorBody(unittest.TestCase):
    def test_redacts_bearer_token(self) -> None:
        redacted = redact_llm_error_body("401 Unauthorized: Authorization: Bearer sk-secret123abc")
        self.assertNotIn("sk-secret123abc", redacted)
        self.assertIn("Bearer [REDACTED]", redacted)

    def test_redacts_standalone_api_key(self) -> None:
        redacted = redact_llm_error_body('{"error":"invalid key sk-ABCDEF0123456789"}')
        self.assertNotIn("sk-ABCDEF0123456789", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_truncates_long_body_with_marker(self) -> None:
        redacted = redact_llm_error_body("x" * 900, max_chars=500)
        self.assertLessEqual(len(redacted), 500 + len("…(truncated)"))
        self.assertTrue(redacted.endswith("…(truncated)"))

    def test_redaction_runs_before_truncation(self) -> None:
        # A secret straddling the cutoff must not be half-leaked: redaction first.
        body = ("a" * 495) + "Bearer sk-tail-secret-value"
        redacted = redact_llm_error_body(body, max_chars=500)
        self.assertNotIn("sk-tail-secret-value", redacted)

    def test_preserves_ordinary_error_text(self) -> None:
        body = '{"error":{"message":"model not found","type":"invalid_request_error"}}'
        self.assertEqual(redact_llm_error_body(body), body)

    def test_handles_empty_body(self) -> None:
        self.assertEqual(redact_llm_error_body(""), "")
