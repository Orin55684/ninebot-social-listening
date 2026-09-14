"""Provider-neutral model gateway types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class DataClassification(str, Enum):
    """Classification applied before content reaches a model provider."""

    SYNTHETIC = "synthetic"
    PUBLIC = "public"
    COMPANY_APPROVED = "company_approved"
    PRODUCTION_CHAT = "production_chat"


class ModelGatewayError(RuntimeError):
    """Base error raised by a model gateway."""


class ModelConfigurationError(ModelGatewayError):
    """The provider is missing required configuration."""


class ModelSecurityError(ModelGatewayError):
    """The request violates the provider's data policy."""


@dataclass(frozen=True)
class ModelRequest:
    """A model request with an explicit data classification."""

    system_prompt: str
    user_prompt: str
    data_classification: DataClassification
    max_tokens: int = 1200
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelResponse:
    """Normalized JSON response returned by any provider."""

    payload: Mapping[str, Any]
    provider: str
    model: str
    usage: Mapping[str, Any] = field(default_factory=dict)


class ModelGateway(ABC):
    """Interface implemented by external and future private model providers."""

    @abstractmethod
    def analyze_json(self, request: ModelRequest) -> ModelResponse:
        """Return a validated JSON object for one analysis request."""

