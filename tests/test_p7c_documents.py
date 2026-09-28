"""P7c local document reader behavior."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from src.core.schemas import ToolContext
from src.tools.document_tools import DOCUMENT_TOOL_DEF, make_document_tool


def _context(root: Path) -> ToolContext:
    return ToolContext(root, DOCUMENT_TOOL_DEF)


def test_document_read_returns_located_text_segments(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("first\nsecond\nthird", encoding="utf-8")
    tool = make_document_tool({})

    result = tool.handler({"path": "notes.md"}, _context(tmp_path))

    assert result["path"] == "notes.md"
    assert result["format"] == "md"
    assert result["extraction"] == "ok"
    assert result["segments"][0]["locator"] == {
        "kind": "line_range", "start": 1, "end": 3
    }
    assert result["segments"][0]["text"] == "first\nsecond\nthird"
    assert result["truncated"] is False


def test_document_read_reports_empty_text_file(tmp_path: Path) -> None:
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    tool = make_document_tool({})

    result = tool.handler({"path": "empty.txt"}, _context(tmp_path))

    assert result["extraction"] == "empty"
    assert result["segments"] == []
    assert result["notice"]


def test_document_preflight_rejects_oversized_file(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_text("12345", encoding="utf-8")
    tool = make_document_tool({"max_file_bytes": 4})

    try:
        tool.preflight({"path": "large.txt"}, _context(tmp_path))  # type: ignore[misc]
    except Exception as exc:
        assert getattr(exc, "code", None) == "FILE_ERROR"
        assert getattr(exc, "details", {}).get("reason") == "target_too_large"
    else:
        raise AssertionError("oversized document was accepted")


def test_document_read_rejects_workspace_escape_without_writes(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-p7c.md"
    outside.write_text("private", encoding="utf-8")
    before = {path.relative_to(tmp_path): (path.stat().st_mtime_ns, path.read_bytes())
              for path in tmp_path.rglob("*") if path.is_file()}

    with pytest.raises(Exception) as caught:
        make_document_tool({}).handler({"path": "../outside-p7c.md"}, _context(tmp_path))

    after = {path.relative_to(tmp_path): (path.stat().st_mtime_ns, path.read_bytes())
             for path in tmp_path.rglob("*") if path.is_file()}
    assert getattr(caught.value, "details", {}).get("reason") == "workspace_escape"
    assert after == before


def test_document_rejects_unsupported_legacy_format(tmp_path: Path) -> None:
    (tmp_path / "old.doc").write_bytes(b"legacy")
    tool = make_document_tool({})

    try:
        tool.handler({"path": "old.doc"}, _context(tmp_path))
    except Exception as exc:
        assert getattr(exc, "code", None) == "TOOL_EXEC_ERROR"
        assert getattr(exc, "details", {}).get("reason") == "document_unsupported_format"
    else:
        raise AssertionError("legacy document was accepted")


def test_document_distinguishes_legacy_and_unknown_format_messages(tmp_path: Path) -> None:
    (tmp_path / "old.doc").write_bytes(b"legacy")
    (tmp_path / "unknown.xyz").write_bytes(b"unknown")
    tool = make_document_tool({})

    messages: list[str] = []
    for name in ("old.doc", "unknown.xyz"):
        with pytest.raises(Exception) as caught:
            tool.handler({"path": name}, _context(tmp_path))
        messages.append(getattr(caught.value, "user_message", ""))

    assert messages[0] != messages[1]


def test_unexpected_parser_error_names_the_parser(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    monkeypatch.setattr(
        "src.tools.document_tools._extract",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(Exception) as caught:
        make_document_tool({}).handler({"path": "notes.txt"}, _context(tmp_path))

    assert getattr(caught.value, "details", {}).get("reason") == "document_extract_failed"
    assert getattr(caught.value, "details", {}).get("parser") == "text"


def test_document_extraction_stops_and_reports_unknown_total(tmp_path: Path) -> None:
    (tmp_path / "long.md").write_text(
        "\n".join(f"line {index}" for index in range(450)), encoding="utf-8"
    )
    tool = make_document_tool({"max_segments_total": 1})

    result = tool.handler({"path": "long.md"}, _context(tmp_path))

    assert result["truncation_reason"] == "max_segments_total"
    assert result["segments_total"] is None
    assert result["segments_returned"] <= 2
    assert "总数未知" in result["notice"]


def test_pdf_without_text_layer_is_reported_honestly(tmp_path: Path) -> None:
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with (tmp_path / "scan.pdf").open("wb") as stream:
        writer.write(stream)

    result = make_document_tool({}).handler(
        {"path": "scan.pdf"}, _context(tmp_path)
    )

    assert result["extraction"] == "no_text_layer"
    assert result["segments"] == []
    assert "OCR" in result["notice"]


def test_docx_preserves_paragraph_and_table_row_locations(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("paragraph text")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "left"
    table.cell(0, 1).text = "right"
    document.save(tmp_path / "report.docx")

    result = make_document_tool({}).handler(
        {"path": "report.docx"}, _context(tmp_path)
    )

    assert [segment["locator"]["kind"] for segment in result["segments"]] == [
        "paragraph", "table_row"
    ]
    assert result["segments"][1]["text"] == "left\tright"


def test_ooxml_container_mismatch_precedes_parser_availability(
    tmp_path: Path, monkeypatch
) -> None:
    with zipfile.ZipFile(tmp_path / "wrong.xlsx", "w") as archive:
        archive.writestr("word/document.xml", "<document/>")
    monkeypatch.setattr("src.tools.document_tools.importlib.util.find_spec", lambda _name: None)

    with pytest.raises(Exception) as caught:
        make_document_tool({}).handler({"path": "wrong.xlsx"}, _context(tmp_path))

    assert getattr(caught.value, "details", {}).get("reason") == "document_format_mismatch"


def test_valid_container_reports_missing_parser(tmp_path: Path, monkeypatch) -> None:
    with zipfile.ZipFile(tmp_path / "sheet.xlsx", "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
    monkeypatch.setattr("src.tools.document_tools.importlib.util.find_spec", lambda _name: None)

    with pytest.raises(Exception) as caught:
        make_document_tool({}).handler({"path": "sheet.xlsx"}, _context(tmp_path))

    assert getattr(caught.value, "details", {}).get("reason") == "parser_unavailable"
    assert getattr(caught.value, "recoverable", None) is True


def test_ooxml_expansion_limit_precedes_parser(tmp_path: Path, monkeypatch) -> None:
    with zipfile.ZipFile(tmp_path / "sheet.xlsx", "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("extra.bin", "x")
    monkeypatch.setattr(
        "src.tools.document_tools.importlib.util.find_spec",
        lambda _name: (_ for _ in ()).throw(AssertionError("parser lookup must not run")),
    )

    with pytest.raises(Exception) as caught:
        make_document_tool({"max_zip_entries": 1}).handler(
            {"path": "sheet.xlsx"}, _context(tmp_path)
        )

    assert getattr(caught.value, "details", {}).get("reason") == "document_expansion_too_large"


def test_extraction_reports_character_limit_before_segment_limit(tmp_path: Path) -> None:
    (tmp_path / "long.md").write_text("x" * 300 + "\n" + "y" * 300, encoding="utf-8")

    result = make_document_tool({
        "max_extracted_chars": 100,
        "max_segments_total": 1,
        "max_returned_chars": 100,
        "max_returned_segments": 1,
    }).handler({"path": "long.md"}, _context(tmp_path))

    assert result["truncation_reason"] == "max_extracted_chars"
