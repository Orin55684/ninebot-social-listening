"""Model gateway selection without coupling business code to a provider."""

from __future__ import annotations

import os

from .base import ModelConfigurationError, ModelGateway
from .deepseek import DeepSeekConfig, DeepSeekGateway


def create_model_gateway(provider: str | None = None) -> ModelGateway:
    """Build the configured model gateway.

    A future company-private adapter can be added here without changing callers.
    """

    selected = (provider or os.environ.get("MODEL_PROVIDER", "deepseek")).strip()
    if selected == "deepseek":
        return DeepSeekGateway(DeepSeekConfig.from_env())
    raise ModelConfigurationError(f"Unsupported model provider: {selected}")

