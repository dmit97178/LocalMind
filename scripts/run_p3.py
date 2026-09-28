"""Demonstrate the P3 sensitive-operation confirmation flow."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def main() -> None:
    from src.main import bootstrap
    from src.models.mock_backend import MockModelBackend
    from src.safety.identity import IdentityVerifier

    with tempfile.TemporaryDirectory(prefix="localmind-p3-") as directory:
        workspace = Path(directory)
        target = workspace / "demo.txt"
        target.write_text("P3 confirmation succeeded.", encoding="utf-8")
        model = MockModelBackend(
            structured_response={
                "state": "READY",
                "intent_type": "read_file",
                "entities": {"path": str(target)},
                "missing_info": [],
                "suggested_tools": ["file.read"],
                "tool_intent": "local_action",
                "tool_call": {"tool_name": "file.read", "arguments": {"path": "demo.txt"}},
                "risk_draft": "normal",
                "model_confidence": 0.9,
                "reasoning": "P3 demo.",
            }
        )
        config = Path(__file__).parents[1] / "config" / "p6_legacy.example.toml"
        app = bootstrap(str(config), model_backend_override=model)
        try:
            app.id_verifier = IdentityVerifier({"hash_file": str(workspace / "passphrase")})
            app.id_verifier.set_passphrase("demo-passphrase")

            print(app.handle(f"read {target}", session_id="p3-demo"))
            print(app.handle("confirm demo-passphrase", session_id="p3-demo"))
        finally:
            app.shutdown()


if __name__ == "__main__":
    main()
