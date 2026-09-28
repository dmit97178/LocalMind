"""Tests for the P0 builtin tool backend."""

from pathlib import Path

from src.core.interfaces import ToolBackend
from src.core.schemas import ToolDef


def test_builtin_tool_backend_implements_tool_backend() -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend()

    assert isinstance(backend, ToolBackend)


def test_list_tools_returns_default_whitelisted_tool_definitions() -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend()

    tools = backend.list_tools()

    assert [tool.name for tool in tools] == [
        "system.echo",
        "system.get_time",
        "file.read",
        "file.list_dir",
        "file.stat",
        "file.write",
    ]
    assert all(isinstance(tool, ToolDef) for tool in tools)


def test_list_tools_respects_configured_whitelist() -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend({"whitelist": ["system.echo"]})

    assert [tool.name for tool in backend.list_tools()] == ["system.echo"]


def test_active_builtin_capabilities_cover_the_product_tools() -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend({"whitelist": [
        "system.get_time", "file.read", "file.list_dir", "file.stat", "file.write"
    ]}, capabilities_enabled=True)

    assert [item.capability_id for item in backend.list_capabilities()] == [
        "weather.current", "files.read", "files.info", "files.write", "files.search",
        "system.time"
    ]
    assert backend.list_capabilities()[1].tools == (
        "file.read", "file.list_dir", "document.read"
    )


def test_execute_echo_returns_message() -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend()

    result = backend.execute("system.echo", {"message": "hello"})

    assert result.is_ok is True
    assert result.value == {"message": "hello"}


def test_execute_get_time_returns_iso_timestamp() -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend()

    result = backend.execute("system.get_time", {})

    assert result.is_ok is True
    assert result.value is not None
    assert "timestamp" in result.value
    assert "T" in result.value["timestamp"]


def test_execute_file_read_reads_utf8_text(tmp_path: Path) -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    target = tmp_path / "notes.txt"
    target.write_text("hello from file", encoding="utf-8")
    backend = BuiltinToolBackend({"workspace_root": str(tmp_path)})

    result = backend.execute("file.read", {"path": "notes.txt"})

    assert result.is_ok is True
    assert result.value == {"path": "notes.txt", "content": "hello from file"}


def test_execute_file_list_dir_returns_child_names(tmp_path: Path) -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    backend = BuiltinToolBackend({"workspace_root": str(tmp_path)})

    result = backend.execute("file.list_dir", {"path": "."})

    assert result.is_ok is True
    assert result.value == {"path": ".", "entries": ["a.txt", "b.txt"]}


def test_execute_rejects_tool_outside_whitelist() -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend({"whitelist": ["system.echo"]})

    result = backend.execute("file.read", {"path": "anything"})

    assert result.is_err is True
    assert result.error is not None
    assert result.error.code == "TOOL_NOT_FOUND"


def test_execute_returns_param_error_for_missing_required_param() -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend()

    result = backend.execute("file.read", {})

    assert result.is_err is True
    assert result.error is not None
    assert result.error.code == "TOOL_PARAM_ERROR"


def test_file_write_creates_utf8_text_inside_workspace(tmp_path: Path) -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend({"workspace_root": str(tmp_path)})
    result = backend.execute("file.write", {"path": "报告/结果.txt", "content": "完成"})

    assert result.is_ok
    assert result.value == {"path": "报告/结果.txt", "bytes_written": 6}
    assert (tmp_path / "报告" / "结果.txt").read_text(encoding="utf-8") == "完成"


def test_file_write_preflight_promotes_existing_target_to_sensitive(tmp_path: Path) -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    target = tmp_path / "notes.txt"
    target.write_text("old", encoding="utf-8")
    backend = BuiltinToolBackend({"workspace_root": str(tmp_path)})

    report = backend.preflight("file.write", {"path": "notes.txt", "content": "new"})

    assert report.effective_risk == "sensitive"
    assert report.requires_confirmation is True
    assert report.target_exists is True
    assert report.target_key == str(target.resolve())
    assert report.reason == "target_exists"


def test_file_write_new_target_also_requires_confirmation(tmp_path: Path) -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend({"workspace_root": str(tmp_path)})
    tool = next(tool for tool in backend.list_tools() if tool.name == "file.write")
    report = backend.preflight("file.write", {"path": "new.txt", "content": "text"})

    assert tool.risk_level == "sensitive"
    assert report.effective_risk == "sensitive"
    assert report.requires_confirmation is True
    assert report.target_exists is False
    assert not (tmp_path / "new.txt").exists()


def test_file_write_rejects_workspace_escape_in_preflight_and_execute(tmp_path: Path) -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend({"workspace_root": str(tmp_path)})
    params = {"path": "../outside.txt", "content": "no"}

    report = backend.preflight("file.write", params)
    result = backend.execute("file.write", params)

    assert report.effective_risk == "dangerous"
    assert report.reason == "workspace_escape"
    assert result.is_err
    assert result.error is not None
    assert result.error.code == "FILE_ERROR"
    assert not (tmp_path.parent / "outside.txt").exists()


def test_file_write_rejects_absolute_drive_unc_home_and_prefix_escape(tmp_path: Path) -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend({"workspace_root": str(tmp_path)})
    escaped = f"../{tmp_path.name}_evil/out.txt"
    for raw_path in (
        str((tmp_path.parent / "absolute.txt").resolve()),
        r"C:\outside.txt",
        r"\\server\share\outside.txt",
        "~/outside.txt",
        escaped,
    ):
        report = backend.preflight("file.write", {"path": raw_path, "content": "no"})
        result = backend.execute("file.write", {"path": raw_path, "content": "no"})
        assert report.effective_risk == "dangerous"
        assert report.reason == "workspace_escape"
        assert result.is_err and result.error is not None
        assert result.error.code == "FILE_ERROR"


def test_file_write_rejects_non_text_and_oversized_content(tmp_path: Path) -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend({"workspace_root": str(tmp_path)})

    wrong_type = backend.execute("file.write", {"path": "a.txt", "content": 1})
    oversized = backend.execute(
        "file.write", {"path": "b.txt", "content": "x" * 1_000_001}
    )

    assert wrong_type.is_err and wrong_type.error is not None
    assert wrong_type.error.code == "TOOL_PARAM_ERROR"
    assert wrong_type.error.details["reason"] == "param_type"
    assert oversized.is_err and oversized.error is not None
    assert oversized.error.details == {"reason": "content_too_large"}
