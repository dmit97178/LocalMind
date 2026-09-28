"""Pure command parsing and formatting for the interactive CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.core.schemas import LocalMindError
from src.memory.project_store import ProjectStore


class CommandApp(Protocol):
    def status_snapshot(self) -> dict: ...
    def last_turn_report(self) -> dict | None: ...
    def list_projects(self) -> list[str]: ...
    def topics_snapshot(self, session_id: str) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class CommandResult:
    handled: bool
    output: str
    action: str = "none"
    project_id: str | None = None


def handle_command(
    line: str,
    app: CommandApp,
    session_id: str,
    bound_project: str | None,
    trace_on: bool,
) -> CommandResult:
    """Handle only P6a-owned commands; all other text remains untouched."""

    text = line.strip()
    command, _, argument = text.partition(" ")
    command = command.lower()
    argument = argument.strip()
    if command == "/status":
        status = app.status_snapshot()
        return CommandResult(
            True,
            "会话状态："
            f"绑定项目={bound_project or '未归属'}，当前项目={status['project_id'] or '未归属'}，"
            f"话题={status['session_topic'] or '无'}，模型={status['model']}，"
            f"云端={'开' if status['cloud_enabled'] else '关'}，trace={'开' if trace_on else '关'}",
        )
    if command == "/why":
        report = app.last_turn_report()
        if report is None:
            return CommandResult(True, "还没有可说明的上一轮决策。")
        return CommandResult(True, _format_report(report))
    if command == "/projects":
        projects = app.list_projects()
        if not projects:
            return CommandResult(True, "暂无项目。")
        return CommandResult(
            True,
            "项目：" + "，".join(
                f"{project}{'（当前绑定）' if project == bound_project else ''}"
                for project in projects
            ),
        )
    if command == "/topics":
        topics = app.topics_snapshot(session_id)
        return CommandResult(True, "话题：" + (" → ".join(topics) if topics else "暂无"))
    if command == "/switch":
        if not argument:
            return CommandResult(True, f"当前绑定项目：{bound_project or '未归属'}")
        try:
            project_id = ProjectStore.normalize_project_id(argument)
        except LocalMindError as exc:
            return CommandResult(True, exc.user_message)
        return CommandResult(True, f"已绑定项目：{project_id}", "switch_project", project_id)
    if command == "/trace":
        if argument.lower() == "on":
            return CommandResult(True, "trace 已开启。", "trace_on")
        if argument.lower() == "off":
            return CommandResult(True, "trace 已关闭。", "trace_off")
        return CommandResult(True, "用法：/trace on 或 /trace off")
    if command == "/quit":
        return CommandResult(True, "会话已结束，摘要已保存。", "quit")
    return CommandResult(False, "")


def _format_report(report: dict) -> str:
    missing = report.get("missing_info") or ()
    retrieval = report.get("retrieval") or {}
    return "；".join(
        (
            f"上轮动作={report.get('action') or '无'}",
            f"理由={report.get('reason') or '无'}",
            f"理解轮数={report.get('rounds_used', 0)}",
            f"缺失信息={len(missing)}项",
            f"检索命中={retrieval.get('hits', 0)}",
        )
    )
