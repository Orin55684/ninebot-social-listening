"""Development-only DeepSeek model adapter.

This adapter intentionally refuses production chat data. It exists so the
project can validate prompts and structured-output plumbing with synthetic or
public examples while the company-private model API is being confirmed.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .base import (
    DataClassification,
    ModelConfigurationError,
    ModelGateway,
    ModelGatewayError,
    ModelRequest,
    ModelResponse,
    ModelSecurityError,
)

HttpTransport = Callable[[urllib.request.Request, float], bytes]


def _default_transport(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "DeepSeekConfig":
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise ModelConfigurationError(
                "DEEPSEEK_API_KEY is required and must be provided at runtime."
            )

        timeout_text = os.environ.get("DEEPSEEK_TIMEOUT_SECONDS", "60")
        try:
            timeout_seconds = float(timeout_text)
        except ValueError as exc:
            raise ModelConfigurationError(
                "DEEPSEEK_TIMEOUT_SECONDS must be a number."
            ) from exc

        return cls(
            api_key=api_key,
            base_url=os.environ.get(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ).strip(),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash").strip(),
            timeout_seconds=timeout_seconds,
        )


class DeepSeekGateway(ModelGateway):
    """Call DeepSeek's OpenAI-compatible chat completion endpoint."""

    _ALLOWED_DATA = {
        DataClassification.SYNTHETIC,
        DataClassification.PUBLIC,
    }

    def __init__(
        self,
        config: DeepSeekConfig,
        transport: HttpTransport = _default_transport,
    ) -> None:
        if not config.api_key.strip():
            raise ModelConfigurationError("DeepSeek API key cannot be empty.")
        if config.timeout_seconds <= 0:
            raise ModelConfigurationError("DeepSeek timeout must be positive.")
        self._config = config
        self._transport = transport

    def analyze_json(self, request: ModelRequest) -> ModelResponse:
        self._enforce_data_policy(request.data_classification)
        body = self._build_body(request)
        endpoint = f"{self._config.base_url.rstrip('/')}/chat/completions"
        http_request = urllib.request.Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            raw_response = self._transport(
                http_request, self._config.timeout_seconds
            )
            response_data = json.loads(raw_response.decode("utf-8"))
            content = response_data["choices"][0]["message"]["content"]
            payload = json.loads(content)
        except ModelGatewayError:
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ModelGatewayError("DeepSeek request failed.") from exc
        except (KeyError, IndexError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelGatewayError(
                "DeepSeek returned an invalid structured response."
            ) from exc

        if not isinstance(payload, dict):
            raise ModelGatewayError("DeepSeek JSON output must be an object.")

        usage = response_data.get("usage")
        return ModelResponse(
            payload=payload,
            provider="deepseek",
            model=str(response_data.get("model") or self._config.model),
            usage=usage if isinstance(usage, dict) else {},
        )

    def _enforce_data_policy(self, classification: DataClassification) -> None:
        if classification not in self._ALLOWED_DATA:
            raise ModelSecurityError(
                "DeepSeek is restricted to synthetic or public data. "
                "Production community messages require the company-private provider."
            )

    def _build_body(self, request: ModelRequest) -> Mapping[str, Any]:
        system_prompt = request.system_prompt.strip()
        if "json" not in system_prompt.lower():
            system_prompt = (
                f"{system_prompt}\nReturn one valid JSON object and no other text."
            ).strip()

        return {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0.2,
            "max_tokens": request.max_tokens,
            "stream": False,
        }

