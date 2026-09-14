from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ninebot_listening.models import (  # noqa: E402
    CompanyPrivateConfig,
    CompanyPrivateGateway,
    DataClassification,
    ModelConfigurationError,
    ModelRequest,
    ModelSecurityError,
    create_model_gateway,
)


class CompanyPrivateGatewayTests(unittest.TestCase):
    def test_returns_normalized_json_for_synthetic_data(self) -> None:
        captured = {}

        def transport(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return json.dumps(
                {
                    "model": "deepseek-v4-flash-0731",
                    "choices": [
                        {"message": {"content": '{"risk_level":"R2"}'}}
                    ],
                    "usage": {"total_tokens": 36},
                }
            ).encode("utf-8")

        gateway = CompanyPrivateGateway(
            CompanyPrivateConfig(
                api_key="test-key",
                base_url="https://company-model.example/v1",
                timeout_seconds=15,
            ),
            transport=transport,
        )
        response = gateway.analyze_json(
            ModelRequest(
                system_prompt="Return JSON.",
                user_prompt="Company-approved synthetic fixture.",
                data_classification=DataClassification.SYNTHETIC,
            )
        )

        self.assertEqual(response.provider, "company_private")
        self.assertEqual(response.payload["risk_level"], "R2")
        self.assertEqual(
            captured["url"],
            "https://company-model.example/v1/chat/completions",
        )
        self.assertEqual(captured["timeout"], 15)
        self.assertEqual(
            captured["body"]["model"], "deepseek-v4-flash-0731"
        )

    def test_rejects_internal_data_by_default_before_network_call(self) -> None:
        called = False

        def transport(_request, _timeout):
            nonlocal called
            called = True
            return b"{}"

        gateway = CompanyPrivateGateway(
            CompanyPrivateConfig(
                api_key="test-key",
                base_url="https://company-model.example/v1",
            ),
            transport=transport,
        )

        for classification in (
            DataClassification.COMPANY_APPROVED,
            DataClassification.PRODUCTION_CHAT,
        ):
            with self.subTest(classification=classification):
                with self.assertRaises(ModelSecurityError):
                    gateway.analyze_json(
                        ModelRequest(
                            system_prompt="Return JSON.",
                            user_prompt="Internal content must remain blocked.",
                            data_classification=classification,
                        )
                    )

        self.assertFalse(called)

    def test_allows_internal_data_only_after_explicit_enablement(self) -> None:
        def transport(_request, _timeout):
            return json.dumps(
                {
                    "choices": [{"message": {"content": '{"ok":true}'}}]
                }
            ).encode("utf-8")

        gateway = CompanyPrivateGateway(
            CompanyPrivateConfig(
                api_key="test-key",
                base_url="https://company-model.example/v1",
                allow_production_data=True,
            ),
            transport=transport,
        )
        for classification in (
            DataClassification.COMPANY_APPROVED,
            DataClassification.PRODUCTION_CHAT,
        ):
            with self.subTest(classification=classification):
                response = gateway.analyze_json(
                    ModelRequest(
                        system_prompt="Return JSON.",
                        user_prompt=(
                            "Synthetic stand-in for an approved production flow."
                        ),
                        data_classification=classification,
                    )
                )
                self.assertTrue(response.payload["ok"])

    def test_factory_selects_company_private_provider(self) -> None:
        previous = {
            key: os.environ.get(key)
            for key in (
                "COMPANY_MODEL_API_KEY",
                "COMPANY_MODEL_BASE_URL",
                "COMPANY_MODEL_ALLOW_PRODUCTION_DATA",
            )
        }
        os.environ["COMPANY_MODEL_API_KEY"] = "test-key"
        os.environ["COMPANY_MODEL_BASE_URL"] = (
            "https://company-model.example/v1"
        )
        os.environ["COMPANY_MODEL_ALLOW_PRODUCTION_DATA"] = "false"
        try:
            gateway = create_model_gateway("company_private")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertIsInstance(gateway, CompanyPrivateGateway)

    def test_environment_requires_api_key(self) -> None:
        old_value = os.environ.pop("COMPANY_MODEL_API_KEY", None)
        try:
            with self.assertRaises(ModelConfigurationError):
                CompanyPrivateConfig.from_env()
        finally:
            if old_value is not None:
                os.environ["COMPANY_MODEL_API_KEY"] = old_value

    def test_invalid_production_flag_is_rejected(self) -> None:
        previous = {
            key: os.environ.get(key)
            for key in (
                "COMPANY_MODEL_API_KEY",
                "COMPANY_MODEL_BASE_URL",
                "COMPANY_MODEL_ALLOW_PRODUCTION_DATA",
            )
        }
        os.environ["COMPANY_MODEL_API_KEY"] = "test-key"
        os.environ["COMPANY_MODEL_BASE_URL"] = (
            "https://company-model.example/v1"
        )
        os.environ["COMPANY_MODEL_ALLOW_PRODUCTION_DATA"] = "maybe"
        try:
            with self.assertRaises(ModelConfigurationError):
                CompanyPrivateConfig.from_env()
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
