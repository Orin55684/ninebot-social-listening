"""Adapter for the company-approved OpenAI-compatible model service."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .base import DataClassification, ModelConfigurationError
from .openai_compatible import (
    HttpTransport,
    OpenAICompatibleGateway,
    default_transport,
)


def _read_boolean(name: str, default: bool = False) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ModelConfigurationError(
        f"{name} must be true or false, not {raw_value!r}."
    )


@dataclass(frozen=True)
class CompanyPrivateConfig:
    api_key: str
    base_url: str
    model: str = "deepseek-v4-flash-0731"
    timeout_seconds: float = 60.0
    allow_production_data: bool = False

    @classmethod
    def from_env(cls) -> "CompanyPrivateConfig":
        api_key = os.environ.get("COMPANY_MODEL_API_KEY", "").strip()
        if not api_key:
            raise ModelConfigurationError(
                "COMPANY_MODEL_API_KEY is required and must be provided at runtime."
            )

        timeout_text = os.environ.get("COMPANY_MODEL_TIMEOUT_SECONDS", "60")
        try:
            timeout_seconds = float(timeout_text)
        except ValueError as exc:
            raise ModelConfigurationError(
                "COMPANY_MODEL_TIMEOUT_SECONDS must be a number."
            ) from exc

        base_url = os.environ.get("COMPANY_MODEL_BASE_URL", "").strip()
        if not base_url:
            raise ModelConfigurationError(
                "COMPANY_MODEL_BASE_URL is required and must be provided at runtime."
            )

        return cls(
            api_key=api_key,
            base_url=base_url,
            model=os.environ.get(
                "COMPANY_MODEL_NAME", "deepseek-v4-flash-0731"
            ).strip(),
            timeout_seconds=timeout_seconds,
            allow_production_data=_read_boolean(
                "COMPANY_MODEL_ALLOW_PRODUCTION_DATA", default=False
            ),
        )


class CompanyPrivateGateway(OpenAICompatibleGateway):
    """Use the company service while preserving explicit data approval gates."""

    _PROVIDER = "company_private"
    _ALLOWED_DATA = frozenset(
        {
            DataClassification.SYNTHETIC,
            DataClassification.PUBLIC,
        }
    )
    _DATA_POLICY_ERROR = (
        "Internal community data is disabled for the company model until "
        "service-account, logging, retention, and data-approval checks are complete."
    )

    def __init__(
        self,
        config: CompanyPrivateConfig,
        transport: HttpTransport = default_transport,
    ) -> None:
        super().__init__(config, transport)
        self._company_config = config

    def _is_data_allowed(self, classification: DataClassification) -> bool:
        if classification in {
            DataClassification.COMPANY_APPROVED,
            DataClassification.PRODUCTION_CHAT,
        }:
            return self._company_config.allow_production_data
        return super()._is_data_allowed(classification)
