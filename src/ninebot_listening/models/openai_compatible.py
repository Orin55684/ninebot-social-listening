"""Shared implementation for OpenAI-compatible chat completion services."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping, Protocol

from .base import (
    DataClassification,
    ModelConfigurationError,
    ModelGateway,
    ModelGatewayError,
    ModelRequest,
    ModelResponse,
    ModelSecurityError,
)


class OpenAICompatibleConfig(Protocol):
    """Configuration fields required by the shared gateway."""

    api_key: str
    base_url: str
    model: str
    timeout_seconds: float


HttpTransport = Callable[[urllib.request.Request, float], bytes]


def default_transport(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class OpenAICompatibleGateway(ModelGateway):
    """Normalize JSON responses from an OpenAI-compatible model endpoint."""

    _PROVIDER = "openai_compatible"
    _ALLOWED_DATA: frozenset[DataClassification] = frozenset()
    _DATA_POLICY_ERROR = "This provider is not approved for the requested data."

    def __init__(
        self,
        config: OpenAICompatibleConfig,
        transport: HttpTransport = default_transport,
    ) -> None:
        if not config.api_key.strip():
            raise ModelConfigurationError(
                f"{self._PROVIDER} API key cannot be empty."
            )
        if not config.base_url.strip():
            raise ModelConfigurationError(
                f"{self._PROVIDER} base URL cannot be empty."
            )
        if not config.model.strip():
            raise ModelConfigurationError(
                f"{self._PROVIDER} model cannot be empty."
            )
        if config.timeout_seconds <= 0:
            raise ModelConfigurationError(
                f"{self._PROVIDER} timeout must be positive."
            )
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
            raise ModelGatewayError(
                f"{self._PROVIDER} request failed."
            ) from exc
        except (
            KeyError,
            IndexError,
            TypeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ModelGatewayError(
                f"{self._PROVIDER} returned an invalid structured response."
            ) from exc

        if not isinstance(payload, dict):
            raise ModelGatewayError(
                f"{self._PROVIDER} JSON output must be an object."
            )

        usage = response_data.get("usage")
        return ModelResponse(
            payload=payload,
            provider=self._PROVIDER,
            model=str(response_data.get("model") or self._config.model),
            usage=usage if isinstance(usage, dict) else {},
        )

    def _enforce_data_policy(self, classification: DataClassification) -> None:
        if not self._is_data_allowed(classification):
            raise ModelSecurityError(self._DATA_POLICY_ERROR)

    def _is_data_allowed(self, classification: DataClassification) -> bool:
        return classification in self._ALLOWED_DATA

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
