from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ninebot_listening.models import (  # noqa: E402
    DataClassification,
    ModelConfigurationError,
    ModelRequest,
    ModelSecurityError,
    create_model_gateway,
)
from ninebot_listening.models.deepseek import (  # noqa: E402
    DeepSeekConfig,
    DeepSeekGateway,
)


class DeepSeekGatewayTests(unittest.TestCase):
    def test_rejects_production_chat_before_network_call(self) -> None:
        called = False

        def transport(_request, _timeout):
            nonlocal called
            called = True
            return b"{}"

        gateway = DeepSeekGateway(
            DeepSeekConfig(api_key="test-key"), transport=transport
        )

        with self.assertRaises(ModelSecurityError):
            gateway.analyze_json(
                ModelRequest(
                    system_prompt="Return JSON.",
                    user_prompt="A real community message would be blocked.",
                    data_classification=DataClassification.PRODUCTION_CHAT,
                )
            )

        self.assertFalse(called)

    def test_parses_json_output_for_synthetic_data(self) -> None:
        captured = {}

        def transport(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return json.dumps(
                {
                    "model": "deepseek-flash",
                    "choices": [
                        {"message": {"content": '{"risk_level":"R3"}'}}
                    ],
                    "usage": {"total_tokens": 42},
                }
            ).encode("utf-8")

        gateway = DeepSeekGateway(
            DeepSeekConfig(api_key="test-key", timeout_seconds=12),
            transport=transport,
        )
        response = gateway.analyze_json(
            ModelRequest(
                system_prompt="Classify this example.",
                user_prompt="Synthetic example: the display does not turn on.",
                data_classification=DataClassification.SYNTHETIC,
            )
        )

        self.assertEqual(response.payload["risk_level"], "R3")
        self.assertEqual(captured["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(captured["timeout"], 12)
        self.assertEqual(
            captured["body"]["response_format"], {"type": "json_object"}
        )
        self.assertIn("json", captured["body"]["messages"][0]["content"].lower())

    def test_environment_requires_api_key(self) -> None:
        old_value = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            with self.assertRaises(ModelConfigurationError):
                DeepSeekConfig.from_env()
        finally:
            if old_value is not None:
                os.environ["DEEPSEEK_API_KEY"] = old_value

    def test_factory_rejects_unknown_provider(self) -> None:
        with self.assertRaises(ModelConfigurationError):
            create_model_gateway("unknown")


if __name__ == "__main__":
    unittest.main()
