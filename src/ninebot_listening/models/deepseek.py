"""Development-only DeepSeek model adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .base import (
    DataClassification,
    ModelConfigurationError,
)
from .openai_compatible import OpenAICompatibleGateway


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


class DeepSeekGateway(OpenAICompatibleGateway):
    """Call DeepSeek's OpenAI-compatible chat completion endpoint."""

    _PROVIDER = "deepseek"
    _ALLOWED_DATA = frozenset(
        {
            DataClassification.SYNTHETIC,
            DataClassification.PUBLIC,
        }
    )
    _DATA_POLICY_ERROR = (
        "DeepSeek is restricted to synthetic or public data. "
        "Production community messages require the company-private provider."
    )
