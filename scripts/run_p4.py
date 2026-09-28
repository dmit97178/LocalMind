"""Run an offline P4 cloud-advisory demonstration without network access."""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.mock_backend import MockModelBackend  # noqa: E402


class FakeTransport:
    """Return one deterministic OpenAI-compatible response."""

    def post_json(self, path: str, payload: dict, headers: dict) -> dict:
        del path, payload, headers
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "analysis": "Compare the available indexes before changing queries.",
                                "risks": ["validate with representative data"],
                            }
                        )
                    }
                }
            ]
        }


class DemoModel(MockModelBackend):
    """Produce the initial cloud-eligible intent, then a local answer intent."""

    def __init__(self) -> None:
        super().__init__(text_response="本地整合建议：先检查索引与查询计划。")
        self._responses = [
            {
                "state": "READY",
                "intent_type": "analysis",
                "entities": {"target": "database"},
                "missing_info": [],
                "suggested_tools": [],
                "risk_draft": "normal",
                "model_confidence": 0.9,
                "consultation_proposal": {
                    "should_consult": True,
                    "escalation_reason": "architecture_tradeoff",
                    "expected_benefit": 0.9,
                    "candidate_context": [
                        {"category": "user_entity", "label": "language", "value": "python"}
                    ],
                },
            },
            {
                "state": "READY",
                "intent_type": "analysis",
                "entities": {"target": "database"},
                "missing_info": [],
                "suggested_tools": [],
                "risk_draft": "normal",
                "model_confidence": 0.9,
            },
        ]

    def generate(self, prompt: str, response_schema: dict | None = None) -> dict:
        if response_schema is not None:
            self._ensure_loaded("generate")
            return deepcopy(self._responses.pop(0))
        return super().generate(prompt, response_schema)


def main() -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry
    from src.adapters.openai_compat_adapter import OpenAICompatibleAdvisoryBackend
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap
    from src.safety.cloud_boundary import CloudBoundary
    from src.safety.side_effect_gateway import SideEffectGateway

    os.environ.setdefault("LOCALMIND_DEEPSEEK_API_KEY", "offline-demo-key")
    cloud_backend = OpenAICompatibleAdvisoryBackend(
        CloudProviderRegistry.resolve("deepseek"),
        "deepseek-v4-flash",
        60,
        transport=FakeTransport(),
    )
    app = bootstrap("config/p6_legacy.example.toml", model_backend_override=DemoModel())
    try:
        app.cloud_enabled = True
        app.privacy_policy.mode = "convenient"
        app.cloud_service = CloudAdvisoryService(
            gateway=SideEffectGateway(
                boundary=CloudBoundary(), cloud_backend=cloud_backend,
                authorization=app.authorization, audit_log=[]
            )
        )

        prompt = app.handle("分析数据库性能", session_id="p4-demo")
        if "确认" in prompt:
            prompt = app.handle("/cloud allow", session_id="p4-demo")
        print(prompt)
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
