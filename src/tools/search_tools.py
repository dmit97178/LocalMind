"""Deterministic, bounded search inside the configured workspace."""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import cast

from src.core.schemas import PreflightReport, ToolContext, ToolDef, ToolError
from src.core.subprocess_env import restricted_subprocess_environment
from src.tools.file_tools import (
    _preflight_target,
    _require_directory,
    resolve_workspace_target,
)

_DEFAULTS = {
    "max_results": 50,
    "max_results_per_file": 5,
    "max_line_chars": 500,
    "context_lines": 1,
    "timeout_ms": 5000,
    "max_file_bytes": 2 * 1024 * 1024,
    "ignore": (),
}
_IGNORED_DIRS = frozenset(
    {".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env", "node_modules",
     ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "build", "dist", ".idea",
     ".vscode", ".eggs"}
)
_BINARY_SUFFIXES = frozenset(
    {".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe", ".bin", ".o", ".a", ".zip",
     ".gz", ".tar", ".7z", ".rar", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico",
     ".webp", ".mp3", ".mp4", ".avi", ".mov", ".wav", ".pdf", ".docx", ".xlsx",
     ".pptx", ".doc", ".xls", ".ppt", ".sqlite", ".db", ".woff", ".woff2", ".ttf",
     ".otf"}
)
_TRUNCATION_MARKER = "…[已截断]"

SEARCH_TOOL_DEF = ToolDef(
    name="file.search",
    description=(
        "在工作区内搜索文件。mode=filename 按文件名子串匹配，mode=content 按文件内容做"
        "固定字符串（非正则）搜索；返回稳定排序的相对路径、行号和有限上下文。"
        "只搜索工作区，默认忽略隐藏条目、版本控制目录、缓存目录、虚拟环境与二进制文件。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"}, "mode": {"type": "string"},
            "path": {"type": "string"}, "glob": {"type": "string"},
        },
        "required": ["query", "mode"],
    },
    risk_level="normal",
    result_delivery="model_summary",
)


def make_search_tool(settings: dict):
    from src.tools.registry import RegisteredTool

    limits = {**_DEFAULTS, **settings}

    def handler(params: dict, context: ToolContext) -> dict:
        return search_workspace(params, context, limits)

    def preflight(params: dict, context: ToolContext) -> PreflightReport:
        return preflight_search(params, context, limits)

    return RegisteredTool(SEARCH_TOOL_DEF, handler, preflight)


def preflight_search(
    params: dict, context: ToolContext, limits: dict[str, object]
) -> PreflightReport:
    _validate_query(params)
    target = _preflight_target({"path": params.get("path", ".")}, context)
    if isinstance(target, PreflightReport):
        return target
    _require_directory(target)
    return PreflightReport(
        effective_risk="normal", requires_confirmation=False,
        target_exists=True, target_key=str(target),
        approval_profile=context.tool_def.approval_profile,
    )


def search_workspace(
    params: dict, context: ToolContext, limits: dict[str, object]
) -> dict:
    query, mode, pattern = _validate_query(params)
    timeout_ms = _int_limit(limits, "timeout_ms")
    max_file_bytes = _int_limit(limits, "max_file_bytes")
    context_lines = _int_limit(limits, "context_lines", allow_zero=True)
    max_line_chars = _int_limit(limits, "max_line_chars")
    max_results_per_file = _int_limit(limits, "max_results_per_file")
    max_results = _int_limit(limits, "max_results")
    root = resolve_workspace_target(params.get("path", "."), context.workspace_root)
    _require_directory(root)
    started = time.monotonic()
    deadline = started + timeout_ms / 1000
    skipped: dict[str, int | None] = {
        "binary": 0, "too_large": 0, "unreadable": 0, "outside": 0
    }
    raw_ignore = limits.get("ignore", ())
    ignore = tuple(str(item) for item in cast(list[str] | tuple[str, ...], raw_ignore))
    candidates: list[Path] = []
    try:
        for current, dirnames, filenames in os.walk(root, followlinks=False):
            _check_deadline(deadline, timeout_ms)
            dirnames[:] = [name for name in dirnames if not _ignored_path(
                Path(current) / name, context.workspace_root, ignore
            ) and not (Path(current) / name).is_symlink()]
            for name in filenames:
                _check_deadline(deadline, timeout_ms)
                path = Path(current) / name
                if _ignored_path(path, context.workspace_root, ignore) or path.is_symlink():
                    continue
                relative = path.relative_to(context.workspace_root).as_posix()
                if pattern is not None and not fnmatch.fnmatch(relative, pattern):
                    continue
                candidates.append(path)
    except OSError as exc:
        raise _search_error("search_engine_error", "工作区搜索失败，请重试。") from exc

    engine = "python"
    fallback_reason: str | None = None
    all_results: list[dict[str, object]]
    if mode == "filename":
        folded_query = query.casefold()
        all_results = [
            {"path": path.relative_to(context.workspace_root).as_posix(), "name": path.name}
            for path in candidates if folded_query in path.name.casefold()
        ]
    else:
        eligible: list[Path] = []
        for path in candidates:
            _check_deadline(deadline, timeout_ms)
            if path.suffix.lower() in _BINARY_SUFFIXES:
                skipped["binary"] = int(skipped["binary"] or 0) + 1
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    skipped["too_large"] = int(skipped["too_large"] or 0) + 1
                    continue
                with path.open("rb") as stream:
                    if b"\0" in stream.read(8192):
                        skipped["binary"] = int(skipped["binary"] or 0) + 1
                        continue
            except OSError:
                skipped["unreadable"] = int(skipped["unreadable"] or 0) + 1
                continue
            eligible.append(path)
        rg = shutil.which("rg")
        if rg is None:
            fallback_reason = "ripgrep_missing"
        else:
            try:
                matched = _ripgrep_candidates(
                    rg, root, query, pattern, ignore, max_file_bytes,
                    max(0.001, deadline - time.monotonic()),
                )
            except subprocess.TimeoutExpired as exc:
                raise _search_error(
                    "search_timeout",
                    f"搜索超过 {timeout_ms} 毫秒限制，请缩小范围。",
                ) from exc
            except (OSError, ValueError, json.JSONDecodeError):
                fallback_reason = "ripgrep_failed"
            else:
                if matched is not None:
                    eligible = [path for path in eligible if path in matched]
                    engine = "ripgrep"
                    skipped["unreadable"] = None
                else:
                    fallback_reason = "ripgrep_failed"
        all_results = []
        for path in eligible:
            _check_deadline(deadline, timeout_ms)
            try:
                raw = path.read_bytes()
                lines = raw.decode("utf-8", errors="replace").splitlines()
            except OSError:
                if engine != "ripgrep":
                    skipped["unreadable"] = int(skipped["unreadable"] or 0) + 1
                continue
            matches: list[dict[str, object]] = []
            for index, line in enumerate(lines):
                if query not in line:
                    continue
                before = lines[max(0, index - context_lines):index]
                after = lines[index + 1:index + 1 + context_lines]
                matches.append({
                    "line_number": index + 1,
                    "line": _bounded_line(line, max_line_chars),
                    "context_before": [_bounded_line(item, max_line_chars) for item in before],
                    "context_after": [_bounded_line(item, max_line_chars) for item in after],
                })
            matches = sorted(matches, key=lambda item: cast(int, item["line_number"]))[
                :max_results_per_file
            ]
            if matches:
                all_results.append({
                    "path": path.relative_to(context.workspace_root).as_posix(),
                    "matches": matches,
                })

    workspace = context.workspace_root.resolve()
    contained, containment_notice = _filter_contained_results(
        all_results, workspace, skipped
    )
    contained.sort(key=lambda item: str(item["path"]))
    if mode == "content":
        total = sum(len(cast(list[dict[str, object]], item["matches"])) for item in contained)
        remaining = max_results
        returned: list[dict[str, object]] = []
        for item in contained:
            if remaining <= 0:
                break
            matches = cast(list[dict[str, object]], item["matches"])[:remaining]
            if matches:
                returned.append({**item, "matches": matches})
                remaining -= len(matches)
        returned_count = sum(
            len(cast(list[dict[str, object]], item["matches"])) for item in returned
        )
    else:
        total = len(contained)
        returned = contained[:max_results]
        returned_count = len(returned)
    truncated = returned_count < total
    truncation_notice = (
        f"共有 {total} 个结果，本次返回 {returned_count} 个；"
        f"剩余 {total-returned_count} 个未返回。" if truncated else None
    )
    notice = " ".join(
        item for item in (containment_notice, truncation_notice) if item
    ) or None
    return {
        "mode": mode, "root": root.relative_to(workspace).as_posix() or ".", "query": query,
        "engine": engine, "fallback_reason": fallback_reason,
        "results": returned, "result_count": returned_count,
        "file_count": len({item["path"] for item in returned}),
        "results_truncated": truncated, "skipped": skipped, "notice": notice,
        "elapsed_ms": max(0, int((time.monotonic() - started) * 1000)),
    }


def _validate_query(params: dict) -> tuple[str, str, str | None]:
    query = params.get("query")
    mode = params.get("mode")
    if not isinstance(query, str) or not query.strip():
        raise _search_error("query_invalid", "搜索内容不能为空。")
    if mode not in {"filename", "content"}:
        raise _search_error("query_invalid", "搜索模式必须是 filename 或 content。", param="mode")
    pattern = params.get("glob")
    if pattern is not None:
        if (
            not isinstance(pattern, str) or not pattern or len(pattern) > 256
            or "\0" in pattern or "\\" in pattern or pattern.startswith("/")
            or Path(pattern).drive or ".." in Path(pattern).parts
            or any(ord(char) < 32 or 127 <= ord(char) < 160 for char in pattern)
        ):
            raise _search_error("glob_invalid", "搜索文件过滤表达式无效。")
    return query, str(mode), pattern


def _int_limit(limits: dict[str, object], key: str, *, allow_zero: bool = False) -> int:
    value = limits[key]
    minimum = 0 if allow_zero else 1
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise _search_error("search_engine_error", "搜索配置无效。", config_key=key)
    return value


def _filter_contained_results(
    results: list[dict[str, object]],
    workspace: Path,
    skipped: dict[str, int | None],
) -> tuple[list[dict[str, object]], str | None]:
    """Recheck result paths at the final return boundary."""

    contained: list[dict[str, object]] = []
    removed = 0
    workspace = workspace.resolve()
    for item in results:
        try:
            candidate = (workspace / str(item["path"])).resolve()
            if not candidate.is_relative_to(workspace):
                removed += 1
                continue
        except (OSError, ValueError):
            removed += 1
            continue
        contained.append(item)
    if removed:
        skipped["outside"] = int(skipped.get("outside") or 0) + removed
        return contained, f"已丢弃 {removed} 个越出工作区边界的搜索结果。"
    return contained, None


def _ripgrep_candidates(
    executable: str,
    root: Path,
    query: str,
    pattern: str | None,
    configured_ignore: tuple[str, ...],
    max_file_bytes: int,
    timeout_seconds: float,
) -> set[Path] | None:
    """Return matching regular files; None means rg failed and Python must retry."""

    command = [
        executable,
        "--json",
        "--fixed-strings",
        "--no-config",
        "--no-ignore",
        "--color=never",
        f"--max-filesize={max_file_bytes}",
    ]
    for name in sorted(_IGNORED_DIRS):
        command.extend(("--glob", f"!**/{name}/**"))
    for suffix in sorted(_BINARY_SUFFIXES):
        command.extend(("--glob", f"!*{suffix}"))
    for ignored in configured_ignore:
        command.extend(("--glob", f"!{ignored}"))
    if pattern is not None:
        command.extend(("--glob", pattern))
    command.extend(("--", query, str(root)))
    process = subprocess.Popen(
        command,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=restricted_subprocess_environment(),
        shell=False,
    )
    try:
        stdout, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise
    if process.returncode not in {0, 1, 2}:
        return None
    if process.returncode == 1:
        return set()
    matches: set[Path] = set()
    for raw_line in stdout.splitlines():
        event = json.loads(raw_line)
        if event.get("type") != "match":
            continue
        data = event.get("data", {})
        path_data = data.get("path", {}) if isinstance(data, dict) else {}
        text = path_data.get("text") if isinstance(path_data, dict) else None
        if isinstance(text, str):
            matches.add((root / text).resolve())
    if process.returncode == 2 and not matches:
        return None
    return matches


def _ignored_path(path: Path, workspace: Path, configured: tuple[str, ...]) -> bool:
    name = path.name
    if name.startswith(".") or name in _IGNORED_DIRS or name.endswith(".egg-info"):
        return True
    relative = path.relative_to(workspace).as_posix()
    return any(
        fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(name, pattern)
        for pattern in configured
    )


def _bounded_line(line: str, limit: int) -> str:
    if len(line) <= limit:
        return line
    keep = max(0, limit - len(_TRUNCATION_MARKER))
    return line[:keep] + _TRUNCATION_MARKER


def _check_deadline(deadline: float, timeout_ms: int) -> None:
    if time.monotonic() > deadline:
        raise _search_error(
            "search_timeout", f"搜索超过 {timeout_ms} 毫秒限制，请缩小范围。"
        )


def _search_error(reason: str, user_message: str, **details: object) -> ToolError:
    return ToolError(
        code="TOOL_EXEC_ERROR", message=f"Workspace search failed: {reason}",
        user_message=user_message, recoverable=True,
        details={"reason": reason, **details},
    )
