from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from one_person_dnd.config import LLMConfig
from one_person_dnd.llm.providers import apply_provider_defaults, transport_provider


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


class LLMClientError(RuntimeError):
    pass


class OpenAICompatClient:
    def __init__(self, cfg: LLMConfig) -> None:
        self._cfg = apply_provider_defaults(cfg)

    def _endpoint(self) -> str:
        """
        Accept either:
        - base_url = http://host:port/v1            (preferred)
        - base_url = http://host:port/v1/chat/completions (tolerated)
        """
        base = self._cfg.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = (self._cfg.api_key or "").strip()
        # For local/self-hosted OpenAI-compatible servers, api_key can be empty.
        # Avoid sending an invalid header value like "Bearer ".
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def chat(self, messages: list[ChatMessage]) -> str:
        """
        Non-streaming call to OpenAI-compatible /chat/completions.
        """
        payload: dict[str, Any] = {
            "model": self._cfg.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
        }
        if self._cfg.temperature is not None:
            payload["temperature"] = self._cfg.temperature
        if self._cfg.top_p is not None:
            payload["top_p"] = self._cfg.top_p
        if self._cfg.max_tokens is not None:
            payload["max_tokens"] = self._cfg.max_tokens

        # Make read timeout configurable (models may take >60s).
        # Use small connect/write timeouts to fail fast on networking issues.
        timeout = httpx.Timeout(connect=10.0, read=self._cfg.timeout_seconds, write=10.0, pool=10.0)

        last_exc: Exception | None = None
        for attempt in range(2):  # 1 retry for transient network/read-timeout
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(self._endpoint(), headers=self._headers(), json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                last_exc = None
                break
            except httpx.HTTPStatusError as e:
                body = ""
                try:
                    body = e.response.text
                except Exception:
                    pass
                raise LLMClientError(f"LLM HTTP error: {e} body={body}") from e
            except (httpx.ReadTimeout, httpx.ConnectError) as e:
                last_exc = e
                if attempt == 0:
                    continue
                raise LLMClientError(f"LLM request failed: {e}") from e
            except Exception as e:
                raise LLMClientError(f"LLM request failed: {e}") from e

        if last_exc is not None:
            raise LLMClientError(f"LLM request failed: {last_exc}") from last_exc

        try:
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise LLMClientError(f"Unexpected LLM response shape: {data}") from e

    def chat_stream_sse(self, messages: list[ChatMessage]) -> Iterable[str]:
        """
        Streaming via server-sent events (best-effort). Yields text deltas.

        Note: OpenAI-compatible providers differ slightly; we parse the common shape:
        - data: {"choices":[{"delta":{"content":"..."}}]}
        """
        payload: dict[str, Any] = {
            "model": self._cfg.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }
        if self._cfg.temperature is not None:
            payload["temperature"] = self._cfg.temperature
        if self._cfg.top_p is not None:
            payload["top_p"] = self._cfg.top_p
        if self._cfg.max_tokens is not None:
            payload["max_tokens"] = self._cfg.max_tokens

        # Many OpenAI-compatible servers don't reliably send "data: [DONE]" or close the connection.
        # We therefore treat "no bytes for N seconds" as end-of-stream *if we've already received tokens*.
        # Treat "no bytes for N seconds" as end-of-stream (only after we've received some tokens).
        # Use a relatively generous threshold to avoid prematurely ending streams where the model
        # pauses (thinking) between chunks.
        stream_inactivity_timeout_s = max(90.0, float(self._cfg.timeout_seconds or 0))
        timeout = httpx.Timeout(connect=10.0, read=stream_inactivity_timeout_s, write=10.0, pool=10.0)

        got_any = False
        try:
            with httpx.Client(timeout=timeout) as client:
                with client.stream("POST", self._endpoint(), headers=self._headers(), json=payload) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue
                        data_str = line[len("data:") :].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = httpx.Response(200, content=data_str).json()
                        except Exception:
                            continue
                        try:
                            delta = data["choices"][0].get("delta") or {}
                            content = delta.get("content")
                            if content:
                                got_any = True
                                yield content
                        except Exception:
                            continue
        except httpx.ReadTimeout as e:
            # If the model/provider paused too long or never closed the stream:
            # - If we already got tokens, finalize upstream with what we have.
            # - If we got nothing, treat as a real error.
            if got_any:
                return
            raise LLMClientError(f"LLM stream timed out before any data: {e}") from e
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.text
            except Exception:
                pass
            raise LLMClientError(f"LLM HTTP error: {e} body={body}") from e
        except Exception as e:
            raise LLMClientError(f"LLM request failed: {e}") from e


def create_llm_client(cfg: LLMConfig) -> OpenAICompatClient:
    """
    Factory for selecting LLM provider implementation.

    Current: OpenAI-compatible transports, including provider presets such as DeepSeek.
    Future: add OllamaClient etc. and branch by cfg.provider.
    """
    effective = apply_provider_defaults(cfg)
    provider = transport_provider(effective.provider).strip().lower()
    if provider in ("openai_compat", "openai-compatible", "openai"):
        return OpenAICompatClient(effective)

    raise LLMClientError(
        f"Unsupported LLM provider: {cfg.provider}. "
        "Current supported: openai_compat, deepseek. "
        "Future providers (e.g. ollama) can be added via adapters."
    )
