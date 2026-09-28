"""Run the P1 local Ollama demonstration against config/ollama.example.toml."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def main() -> None:
    from src.core.schemas import LocalMindError
    from src.main import bootstrap

    config_path = PROJECT_ROOT / "config" / "ollama.example.toml"
    try:
        app = bootstrap(str(config_path))
    except LocalMindError as exc:
        print(exc.user_message)
        return
    try:
        reply = app.handle(
            "请使用 system.echo 工具回复：LocalMind 已连接本地模型。",
            session_id="p1-demo",
        )
        print(reply)
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
