"""Strict newline-delimited MCP stdio provider."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections.abc import Mapping
from pathlib import Path

from src.core.interfaces import ToolProvider
from src.core.schemas import ProviderSnapshot, Result, ToolCandidate, ToolError
from src.core.subprocess_env import restricted_subprocess_environment
from src.tools.provider_declarations import ProviderDeclaration

_SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05",)
_MAX_REQUEST_BYTES = 32768
_MAX_RESPONSE_BYTES = 65536
_MAX_NOTIFICATIONS = 64
class _ProviderFailure(Exception):
    def __init__(
        self,
        execution_reason: str,
        health_reason: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(execution_reason)
        self.execution_reason = execution_reason
        self.health_reason = health_reason
        self.details = dict(details or {})


class MCPStdioToolProvider(ToolProvider):
    """One-process, one-handshake MCP provider with fail-closed stream semantics."""

    def __init__(
        self,
        declaration: ProviderDeclaration,
        *,
        handshake_timeout_ms: int,
        call_timeout_ms: int,
    ) -> None:
        self.provider_id = declaration.provider_id
        self._declaration = declaration
        self._handshake_timeout = handshake_timeout_ms / 1000
        self._call_timeout = call_timeout_ms / 1000
        self._process: subprocess.Popen[bytes] | None = None
        self._next_id = 1
        self._handshake_attempted = False
        self._healthy = False
        self._closed = False
        self._failure_reason: str | None = None
        self._protocol_version: str | None = None
        self._unhandled_notifications = 0
        self._pagination_ignored = 0
        self._malformed_tool_entries = 0
        self._unsupported_content_count = 0
        self._timeout_count = 0
        self._forced_kill = False
        self._candidates: tuple[ToolCandidate, ...] = ()
        self._lock = threading.Lock()

    def handshake(self) -> ProviderSnapshot:
        with self._lock:
            if self._closed:
                return self._snapshot(())
            if self._handshake_attempted:
                return self._snapshot(self._candidates)
            self._handshake_attempted = True
            deadline = time.monotonic() + self._handshake_timeout
            try:
                self._start()
                initialize = self._request(
                    "initialize",
                    {
                        "protocolVersion": _SUPPORTED_PROTOCOL_VERSIONS[0],
                        "capabilities": {},
                        "clientInfo": {"name": "LocalMind", "version": "1"},
                    },
                    deadline,
                )
                if not isinstance(initialize, dict):
                    raise _ProviderFailure("provider_protocol_error", "handshake_malformed")
                version = initialize.get("protocolVersion")
                if not isinstance(version, str) or version not in _SUPPORTED_PROTOCOL_VERSIONS:
                    self._protocol_version = version if isinstance(version, str) else None
                    raise _ProviderFailure(
                        "provider_protocol_error", "protocol_version_unsupported"
                    )
                self._protocol_version = version
                self._notify("notifications/initialized", {})
                listed = self._request("tools/list", {}, deadline)
                candidates = self._parse_tool_list(listed)
                self._candidates = candidates
                self._healthy = True
                self._failure_reason = None
                return self._snapshot(candidates)
            except _ProviderFailure as exc:
                self._invalidate(exc.health_reason)
                return self._snapshot(())
            except (OSError, ValueError):
                self._invalidate("unreachable")
                return self._snapshot(())

    def execute(self, raw_name: str, params: Mapping[str, object]) -> Result[dict]:
        with self._lock:
            if not self._healthy or self._closed or not self._process_alive():
                if self._healthy:
                    self._invalidate("unreachable")
                return Result.err(self._tool_error("provider_unreachable"))
            try:
                result = self._request(
                    "tools/call",
                    {"name": raw_name, "arguments": dict(params)},
                    time.monotonic() + self._call_timeout,
                )
                return self._parse_call_result(result)
            except _ProviderFailure as exc:
                if exc.execution_reason not in {
                    "tool_reported_error",
                    "provider_unsupported_content",
                    "param_too_large",
                }:
                    self._invalidate(exc.health_reason)
                return Result.err(self._tool_error(exc.execution_reason, exc.details))
            except (OSError, ValueError):
                self._invalidate("unreachable")
                return Result.err(self._tool_error("provider_unreachable"))

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            process = self._process
            self._healthy = False
            self._failure_reason = "closed"
            self._process = None
            if process is None:
                return
            try:
                if process.stdin is not None:
                    process.stdin.close()
            except OSError:
                pass
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        self._forced_kill = True
                        process.kill()
                        process.wait(timeout=1)
                else:
                    process.wait(timeout=0.1)
            except (OSError, subprocess.SubprocessError):
                try:
                    process.kill()
                    process.wait(timeout=0.5)
                    self._forced_kill = True
                except (OSError, subprocess.SubprocessError):
                    pass

    def diagnostics(self) -> dict[str, object]:
        if self._healthy and not self._process_alive():
            self._invalidate("unreachable")
        return {
            "provider_id": self.provider_id,
            "healthy": self._healthy,
            "failure_reason": self._failure_reason,
            "protocol_version": self._protocol_version,
            "unhandled_notifications": self._unhandled_notifications,
            "pagination_ignored": self._pagination_ignored,
            "malformed_tool_entries": self._malformed_tool_entries,
            "unsupported_content_count": self._unsupported_content_count,
            "timeout_count": self._timeout_count,
            "closed": self._closed,
            "close_forced": self._forced_kill,
        }

    def _start(self) -> None:
        environment = restricted_subprocess_environment()
        cwd = Path(__file__).parents[2] if self._declaration.cwd_from_repo_root else None
        self._process = subprocess.Popen(
            list(self._declaration.argv),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=cwd,
            env=environment,
            shell=False,
        )

    def _request(self, method: str, params: dict[str, object], deadline: float) -> object:
        request_id = self._next_id
        self._next_id += 1
        self._write_frame({
            "jsonrpc": "2.0", "id": request_id, "method": method, "params": params,
        })
        notifications = 0
        while True:
            frame = self._read_frame(deadline)
            if "id" not in frame:
                notifications += 1
                self._unhandled_notifications += 1
                if notifications > _MAX_NOTIFICATIONS:
                    raise _ProviderFailure("provider_protocol_error", "protocol")
                continue
            response_id = frame.get("id")
            if (
                isinstance(response_id, bool)
                or not isinstance(response_id, int)
                or response_id != request_id
            ):
                raise _ProviderFailure("provider_protocol_error", "protocol")
            has_result = "result" in frame
            has_error = "error" in frame
            if has_result == has_error:
                raise _ProviderFailure("provider_protocol_error", "protocol")
            if has_error:
                raise _ProviderFailure("provider_protocol_error", "protocol")
            return frame["result"]

    def _notify(self, method: str, params: dict[str, object]) -> None:
        self._write_frame({"jsonrpc": "2.0", "method": method, "params": params})

    def _write_frame(self, payload: dict[str, object]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise _ProviderFailure("provider_unreachable", "unreachable")
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > _MAX_REQUEST_BYTES:
            raise _ProviderFailure("param_too_large", "protocol")
        try:
            process.stdin.write(encoded)
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise _ProviderFailure("provider_unreachable", "unreachable") from exc

    def _read_frame(self, deadline: float) -> dict[str, object]:
        process = self._process
        if process is None or process.stdout is None:
            raise _ProviderFailure("provider_unreachable", "unreachable")
        stdout = process.stdout
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            self._timeout_count += 1
            raise _ProviderFailure("provider_timeout", "timeout")
        result_queue: queue.Queue[bytes | BaseException] = queue.Queue(maxsize=1)

        def read() -> None:
            try:
                result_queue.put(stdout.readline(_MAX_RESPONSE_BYTES + 2))
            except BaseException as exc:  # pragma: no cover - platform pipe failure
                result_queue.put(exc)

        threading.Thread(target=read, daemon=True).start()
        try:
            raw = result_queue.get(timeout=remaining)
        except queue.Empty as exc:
            self._timeout_count += 1
            raise _ProviderFailure("provider_timeout", "timeout") from exc
        if isinstance(raw, BaseException):
            raise _ProviderFailure("provider_unreachable", "unreachable") from raw
        if not raw:
            raise _ProviderFailure("provider_unreachable", "unreachable")
        if len(raw) > _MAX_RESPONSE_BYTES or not raw.endswith(b"\n"):
            raise _ProviderFailure("provider_response_too_large", "oversize")
        try:
            parsed = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _ProviderFailure("provider_parse_error", "protocol") from exc
        if not isinstance(parsed, dict):
            raise _ProviderFailure("provider_protocol_error", "protocol")
        if parsed.get("jsonrpc") != "2.0":
            raise _ProviderFailure("provider_protocol_error", "protocol")
        return parsed

    def _parse_tool_list(self, result: object) -> tuple[ToolCandidate, ...]:
        if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
            raise _ProviderFailure("provider_protocol_error", "protocol")
        if result.get("nextCursor") not in (None, ""):
            self._pagination_ignored += 1
        candidates: list[ToolCandidate] = []
        for item in result["tools"]:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not item["name"]
            ):
                self._malformed_tool_entries += 1
                continue
            schema = item.get("inputSchema", {})
            candidates.append(ToolCandidate(
                raw_name=item["name"],
                input_schema=schema if isinstance(schema, dict) else {},
            ))
        return tuple(candidates)

    def _parse_call_result(self, result: object) -> Result[dict]:
        if not isinstance(result, dict) or not isinstance(result.get("content"), list):
            raise _ProviderFailure("provider_protocol_error", "protocol")
        is_error = result.get("isError", False)
        if not isinstance(is_error, bool):
            raise _ProviderFailure("provider_protocol_error", "protocol")
        content = result["content"]
        if is_error:
            raise _ProviderFailure(
                "tool_reported_error",
                "protocol",
                details={
                    "content_items": len(content),
                    "content_length": sum(
                        len(item.get("text", ""))
                        for item in content
                        if isinstance(item, dict) and isinstance(item.get("text"), str)
                    ),
                },
            )
        if not content:
            raise _ProviderFailure("provider_protocol_error", "protocol")
        texts: list[str] = []
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "text":
                self._unsupported_content_count += 1
                raise _ProviderFailure("provider_unsupported_content", "protocol")
            if not isinstance(item.get("text"), str):
                raise _ProviderFailure("provider_protocol_error", "protocol")
            texts.append(item["text"])
        return Result.ok({"text": "\n".join(texts)})

    def _invalidate(self, reason: str) -> None:
        self._healthy = False
        self._failure_reason = reason
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.3)
                except subprocess.TimeoutExpired:
                    self._forced_kill = True
                    process.kill()
                    process.wait(timeout=1)
            else:
                process.wait(timeout=0.1)
        except (OSError, subprocess.SubprocessError):
            pass

    def _process_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _snapshot(self, candidates: tuple[ToolCandidate, ...]) -> ProviderSnapshot:
        return ProviderSnapshot(
            provider_id=self.provider_id,
            healthy=self._healthy,
            candidates=candidates if self._healthy else (),
            failure_reason=self._failure_reason,
        )

    @staticmethod
    def _tool_error(
        reason: str, extra_details: Mapping[str, object] | None = None
    ) -> ToolError:
        details: dict[str, object] = {"reason": reason}
        details.update(extra_details or {})
        return ToolError(
            code="TOOL_EXEC_ERROR",
            message=f"External tool execution failed: {reason}",
            user_message="外部工具执行失败。",
            recoverable=True,
            details=details,
        )
