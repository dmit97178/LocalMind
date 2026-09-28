"""Terminal renderer for sanitized runtime events."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.core.interfaces import RuntimeEventSink
from src.core.schemas import RuntimeEvent

_ACTION_LABELS = {
    "PLAN_LOCAL": "本地执行",
    "ASK_USER": "请求补充",
    "RETRIEVE_MORE": "继续检索",
    "REQUEST_CLOUD": "请求云端建议",
    "REFUSE": "拒绝",
}


@dataclass
class CliEventSink(RuntimeEventSink):
    writer: Callable[[str], None] = print
    trace_on: bool = False
    run_id: str | None = None
    max_rounds: int = 4

    def set_trace(self, enabled: bool) -> None:
        self.trace_on = enabled

    def emit(self, event: RuntimeEvent) -> None:
        if self.run_id is not None and event.run_id != self.run_id:
            return
        line = self._format_status(event)
        if line is not None:
            self.writer(line)
        elif self.trace_on and event.level == "detail":
            fields = " ".join(f"{key}={value}" for key, value in event.data.items())
            self.writer(f"{event.stage}: {fields}".rstrip())

    def _format_status(self, event: RuntimeEvent) -> str | None:
        data = event.data
        if event.stage == "topic_decision":
            return f"[项目: {data.get('project_id') or '未归属'} | 话题: {data.get('topic_label') or '无'}]"
        if event.stage == "intent_final":
            rounds = data.get("rounds_used", 0)
            state = data.get("final_state", "unknown")
            if rounds == 1 and state == "READY":
                return "[理解: 1 轮收敛]"
            return f"[理解: 第 {rounds}/{self.max_rounds} 轮，{state}]"
        if event.stage == "dispatch_decision":
            confirmation = "（需确认）" if data.get("requires_user_confirmation") else ""
            action = str(data.get("action", "unknown"))
            return f"[决策: {_ACTION_LABELS.get(action, action)}{confirmation}]"
        return None
