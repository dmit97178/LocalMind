"""P7c deterministic workspace search behavior."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from src.core.schemas import ToolContext
from src.tools.search_tools import SEARCH_TOOL_DEF, make_search_tool


def _context(root: Path) -> ToolContext:
    return ToolContext(root, SEARCH_TOOL_DEF)


def test_content_search_is_sorted_and_ignores_hidden_entries(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("TODO b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("TODO a", encoding="utf-8")
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "secret.txt").write_text("TODO secret", encoding="utf-8")
    tool = make_search_tool({})

    result = tool.handler(
        {"query": "TODO", "mode": "content", "path": "."}, _context(tmp_path)
    )

    assert [item["path"] for item in result["results"]] == ["a.txt", "b.txt"]
    assert all(item["matches"][0]["line_number"] == 1 for item in result["results"])
    assert result["result_count"] == 2


def test_filename_search_returns_stable_relative_paths(tmp_path: Path) -> None:
    (tmp_path / "todo.md").write_text("x", encoding="utf-8")
    (tmp_path / "other.md").write_text("x", encoding="utf-8")
    tool = make_search_tool({})

    result = tool.handler(
        {"query": "todo", "mode": "filename", "path": "."}, _context(tmp_path)
    )

    assert result["results"] == [{"path": "todo.md", "name": "todo.md"}]


def test_filename_search_is_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "ReleaseNotes.MD").write_text("done", encoding="utf-8")

    result = make_search_tool({}).handler(
        {"query": "releasenotes", "mode": "filename"}, _context(tmp_path)
    )

    assert [item["path"] for item in result["results"]] == ["ReleaseNotes.MD"]


def test_outside_post_filter_is_injectable_and_emits_notice(tmp_path: Path) -> None:
    from src.tools.search_tools import _filter_contained_results

    skipped: dict[str, int | None] = {"outside": 0}
    kept, notice = _filter_contained_results(
        [{"path": "inside.txt"}, {"path": "../outside.txt"}], tmp_path, skipped
    )

    assert kept == [{"path": "inside.txt"}]
    assert skipped["outside"] == 1
    assert notice


def test_ripgrep_engine_reports_unreadable_as_unknown(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "notes.txt").write_text("needle", encoding="utf-8")
    monkeypatch.setattr("src.tools.search_tools.shutil.which", lambda _name: "rg")
    monkeypatch.setattr(
        "src.tools.search_tools._ripgrep_candidates",
        lambda *_args, **_kwargs: {(tmp_path / "notes.txt").resolve()},
    )

    result = make_search_tool({}).handler(
        {"query": "needle", "mode": "content"}, _context(tmp_path)
    )

    assert result["engine"] == "ripgrep"
    assert result["skipped"]["unreadable"] is None


def test_search_rejects_blank_query_and_invalid_glob(tmp_path: Path) -> None:
    tool = make_search_tool({})
    for params, reason in [
        ({"query": " ", "mode": "content"}, "query_invalid"),
        ({"query": "x", "mode": "content", "glob": "../*.txt"}, "glob_invalid"),
    ]:
        try:
            tool.handler(params, _context(tmp_path))
        except Exception as exc:
            assert getattr(exc, "details", {}).get("reason") == reason
        else:
            raise AssertionError(f"invalid search accepted: {params}")


def test_search_does_not_follow_file_symlinks(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-p7c.txt"
    outside.write_text("SECRET_MATCH", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")
    tool = make_search_tool({})

    result = tool.handler(
        {"query": "SECRET_MATCH", "mode": "content"}, _context(tmp_path)
    )

    assert result["results"] == []


def test_search_combines_builtin_and_configured_ignores(tmp_path: Path) -> None:
    (tmp_path / "visible.txt").write_text("needle", encoding="utf-8")
    (tmp_path / "ignored.log").write_text("needle", encoding="utf-8")
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "secret.txt").write_text("needle", encoding="utf-8")

    result = make_search_tool({"ignore": ["*.log"]}).handler(
        {"query": "needle", "mode": "content"}, _context(tmp_path)
    )

    assert [item["path"] for item in result["results"]] == ["visible.txt"]


def test_content_result_limit_counts_matches_not_files(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.txt").write_text("TODO one\nTODO two\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("TODO three\n", encoding="utf-8")
    monkeypatch.setattr("src.tools.search_tools.shutil.which", lambda _name: None)
    tool = make_search_tool({"max_results": 2, "max_results_per_file": 5})

    result = tool.handler({"query": "TODO", "mode": "content"}, _context(tmp_path))

    assert result["result_count"] == 2
    assert result["file_count"] == 1
    assert result["results_truncated"] is True
    assert "剩余 1" in result["notice"]
    assert result["engine"] == "python"
    assert result["fallback_reason"] == "ripgrep_missing"


def test_binary_detection_and_line_truncation(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "image.png").write_bytes(b"TODO")
    (tmp_path / "fake.txt").write_bytes(b"TODO\0binary")
    (tmp_path / "long.txt").write_text("TODO " + "x" * 100, encoding="utf-8")
    monkeypatch.setattr("src.tools.search_tools.shutil.which", lambda _name: None)
    tool = make_search_tool({"max_line_chars": 20})

    result = tool.handler({"query": "TODO", "mode": "content"}, _context(tmp_path))

    assert result["skipped"]["binary"] >= 2
    assert [item["path"] for item in result["results"]] == ["long.txt"]
    line = result["results"][0]["matches"][0]["line"]
    assert len(line) <= 20 and line.endswith("…[已截断]")


def test_ripgrep_and_python_paths_return_identical_results(tmp_path: Path, monkeypatch) -> None:
    rg = shutil.which("rg")
    if rg is None:
        pytest.skip("ripgrep is not installed")
    (tmp_path / "b.txt").write_text("needle b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("needle a", encoding="utf-8")
    hidden = tmp_path / ".hidden.txt"
    hidden.write_text("needle hidden", encoding="utf-8")
    tool = make_search_tool({})

    ripgrep_result = tool.handler(
        {"query": "needle", "mode": "content"}, _context(tmp_path)
    )
    monkeypatch.setattr("src.tools.search_tools.shutil.which", lambda _name: None)
    python_result = tool.handler(
        {"query": "needle", "mode": "content"}, _context(tmp_path)
    )

    assert ripgrep_result["engine"] == "ripgrep"
    assert python_result["engine"] == "python"
    assert ripgrep_result["results"] == python_result["results"]


def test_ripgrep_timeout_reaps_the_process(tmp_path: Path, monkeypatch) -> None:
    from src.tools.search_tools import _ripgrep_candidates

    real_popen = subprocess.Popen
    spawned: list[subprocess.Popen] = []

    def spawn_sleep(*_args, **kwargs):
        process = real_popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=kwargs.get("cwd"), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=kwargs.get("env"), shell=False,
        )
        spawned.append(process)
        return process

    monkeypatch.setattr("src.tools.search_tools.subprocess.Popen", spawn_sleep)

    with pytest.raises(subprocess.TimeoutExpired):
        _ripgrep_candidates("rg", tmp_path, "needle", None, (), 1024, 0.01)

    assert len(spawned) == 1
    assert spawned[0].poll() is not None
