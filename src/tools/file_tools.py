"""Built-in file tools."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from src.core.schemas import PreflightReport, ToolContext, ToolError

_MAX_WRITE_CHARS = 1_000_000


def read_file(params: dict, context: ToolContext) -> dict:
    path = resolve_workspace_target(params.get("path"), context.workspace_root)
    _require_readable_file(path)
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _file_error("read_failed", "文件读取失败。") from exc
    return {"path": path.relative_to(context.workspace_root).as_posix(), "content": content}


def list_dir(params: dict, context: ToolContext) -> dict:
    path = resolve_workspace_target(params.get("path"), context.workspace_root)
    _require_directory(path)
    try:
        entries = sorted(child.name for child in path.iterdir())
    except OSError as exc:
        raise _file_error("list_failed", "目录读取失败。") from exc
    return {"path": path.relative_to(context.workspace_root).as_posix(), "entries": entries}


def stat_file(params: dict, context: ToolContext) -> dict:
    path = resolve_workspace_target(params.get("path"), context.workspace_root)
    relative = path.relative_to(context.workspace_root).as_posix()
    if not path.exists():
        return {
            "path": relative,
            "exists": False,
            "is_dir": False,
            "size_bytes": None,
            "modified_at": None,
        }
    try:
        metadata = path.stat()
    except OSError as exc:
        raise _file_error("stat_failed", "文件属性读取失败。") from exc
    return {
        "path": relative,
        "exists": True,
        "is_dir": path.is_dir(),
        "size_bytes": metadata.st_size,
        "modified_at": datetime.fromtimestamp(metadata.st_mtime, UTC).isoformat(),
    }


def preflight_read(params: dict, context: ToolContext) -> PreflightReport:
    target = _preflight_target(params, context)
    if isinstance(target, PreflightReport):
        return target
    _require_readable_file(target)
    return PreflightReport(
        effective_risk=context.tool_def.risk_level,
        requires_confirmation=True,
        target_exists=True,
        target_key=str(target),
        approval_profile=context.tool_def.approval_profile,
    )


def preflight_list_dir(params: dict, context: ToolContext) -> PreflightReport:
    target = _preflight_target(params, context)
    if isinstance(target, PreflightReport):
        return target
    _require_directory(target)
    return PreflightReport(
        effective_risk=context.tool_def.risk_level,
        requires_confirmation=False,
        target_exists=True,
        target_key=str(target),
        approval_profile=context.tool_def.approval_profile,
    )


def preflight_stat(params: dict, context: ToolContext) -> PreflightReport:
    target = _preflight_target(params, context)
    if isinstance(target, PreflightReport):
        return target
    return PreflightReport(
        effective_risk=context.tool_def.risk_level,
        requires_confirmation=False,
        target_exists=target.exists(),
        target_key=str(target),
        approval_profile=context.tool_def.approval_profile,
    )


def preflight_write(params: dict, context: ToolContext) -> PreflightReport:
    """Resolve a write target without changing the filesystem."""

    _validated_content(params)
    target = _preflight_target(params, context)
    if isinstance(target, PreflightReport):
        return target
    exists = target.exists()
    if exists and not target.is_file():
        raise _file_error("path_type", "目标路径不是文件。")
    return PreflightReport(
        effective_risk="sensitive",
        requires_confirmation=True,
        target_exists=exists,
        target_key=str(target),
        reason="target_exists" if exists else None,
        approval_profile=context.tool_def.approval_profile,
    )


def write_file(params: dict, context: ToolContext) -> dict:
    content = _validated_content(params)
    target = resolve_workspace_target(params.get("path"), context.workspace_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    relative = target.relative_to(context.workspace_root)
    return {"path": relative.as_posix(), "bytes_written": len(content.encode("utf-8"))}


def resolve_workspace_target(raw_path: object, workspace_root: str | Path) -> Path:
    if not isinstance(raw_path, str):
        raise _file_error("path_type", "文件路径必须是文本。")
    if "\0" in raw_path:
        raise _file_error("path_type", "文件路径无效。")
    if not raw_path.strip() or raw_path.startswith("~"):
        raise _file_error("workspace_escape", "文件操作被拒绝：路径必须位于工作区内。")
    candidate = Path(raw_path)
    if candidate.is_absolute() or candidate.drive or raw_path.startswith(("\\\\", "//")):
        raise _file_error("workspace_escape", "文件操作被拒绝：路径必须位于工作区内。")
    try:
        base = Path(workspace_root).resolve()
        target = (base / candidate).resolve()
    except (OSError, ValueError) as exc:
        raise _file_error("path_type", "文件路径无效。") from exc
    if not target.is_relative_to(base):
        raise _file_error("workspace_escape", "文件操作被拒绝：路径必须位于工作区内。")
    return target


def _preflight_target(
    params: dict,
    context: ToolContext,
) -> Path | PreflightReport:
    try:
        return resolve_workspace_target(params.get("path"), context.workspace_root)
    except ToolError as exc:
        if isinstance(exc.details, dict) and exc.details.get("reason") == "workspace_escape":
            return PreflightReport(
                effective_risk="dangerous",
                requires_confirmation=True,
                reason="workspace_escape",
                approval_profile=context.tool_def.approval_profile,
            )
        raise


def _require_readable_file(path: Path) -> None:
    if not path.exists():
        raise _file_error("target_missing", "目标文件不存在。")
    if not path.is_file():
        raise _file_error("path_type", "目标路径不是文件。")


def _require_directory(path: Path) -> None:
    if not path.exists():
        raise _file_error("target_missing", "目标目录不存在。")
    if not path.is_dir():
        raise _file_error("not_a_directory", "目标路径不是目录。")


def _validated_content(params: dict) -> str:
    content = params.get("content")
    if not isinstance(content, str):
        raise _file_error("content_type", "文件内容必须是文本。")
    if len(content) > _MAX_WRITE_CHARS:
        raise _file_error("content_too_large", "文件内容超过 1000000 字符限制。")
    return content


def _file_error(reason: str, user_message: str) -> ToolError:
    return ToolError(
        code="FILE_ERROR",
        message=f"File operation rejected: {reason}",
        user_message=user_message,
        recoverable=True,
        details={"reason": reason},
    )
