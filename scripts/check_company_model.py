"""Run a safe synthetic smoke test against the company model service."""

from __future__ import annotations

import json

from ninebot_listening.models import (
    DataClassification,
    ModelRequest,
    create_model_gateway,
)


def main() -> None:
    gateway = create_model_gateway("company_private")
    response = gateway.analyze_json(
        ModelRequest(
            system_prompt=(
                "You are a connectivity test. Return one JSON object with keys "
                "status, language, and risk_level. Set status to ok, language to "
                "zh-CN, and risk_level to R4."
            ),
            user_prompt=(
                "合成测试消息：车辆仪表屏幕无法点亮。"
                "仅用于验证模型接口，不是真实用户数据。"
            ),
            data_classification=DataClassification.SYNTHETIC,
            max_tokens=128,
        )
    )
    print(
        json.dumps(
            {
                "request_succeeded": True,
                "provider": response.provider,
                "model": response.model,
                "payload": response.payload,
                "usage": response.usage,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
