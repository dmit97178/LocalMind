"""P7c configuration and production registration contracts."""

from pathlib import Path

import pytest

from src.core.schemas import LocalMindError
from src.main import (
    create_tool_backend,
    normalize_document_config,
    normalize_reflow_config,
    normalize_search_config,
)


def test_p7c_config_defaults_and_zero_context_are_valid() -> None:
    assert normalize_document_config({})["max_file_bytes"] == 33_554_432
    assert normalize_search_config({"context_lines": 0})["context_lines"] == 0
    assert normalize_reflow_config({}) == {"enabled": True, "max_chars": 4000}


def test_bootstrap_injects_enabled_result_reflow() -> None:
    from src.main import bootstrap
    from src.models.mock_backend import MockModelBackend

    app = bootstrap("config/default.toml", model_backend_override=MockModelBackend())

    assert app.reflow is not None
    assert app.reflow.enabled is True


@pytest.mark.parametrize(
    ("normalizer", "value"),
    [
        (normalize_document_config, {"unknown": 1}),
        (normalize_document_config, {"max_file_bytes": True}),
        (normalize_search_config, {"ripgrep_path": "rg"}),
        (normalize_search_config, {"context_lines": 4}),
        (normalize_search_config, {"max_line_chars": 5}),
        (normalize_search_config, {"ignore": ["../escape"]}),
        (normalize_reflow_config, {"timeout_ms": 1}),
    ],
)
def test_p7c_config_is_closed(normalizer, value: object) -> None:
    with pytest.raises(LocalMindError) as caught:
        normalizer(value)
    assert caught.value.details == {"reason": "tool_config_invalid"}


def test_default_registration_activates_both_p7c_tools(tmp_path: Path) -> None:
    backend = create_tool_backend(
        {
            "tool_backend": {
                "type": "builtin_only",
                "config": {
                    "workspace_root": str(tmp_path),
                    "whitelist": ["document.read", "file.search"],
                },
            },
            "tools": {"workspace_root": str(tmp_path)},
            "capability_routing": {"enabled": True},
            "tool_providers": {},
        }
    )

    assert [tool.name for tool in backend.list_tools()] == ["document.read", "file.search"]
    assert [tool.result_delivery for tool in backend.list_tools()] == [
        "model_summary", "model_summary"
    ]


def test_p7c_tool_descriptions_declare_extraction_scope() -> None:
    from src.tools.document_tools import DOCUMENT_TOOL_DEF

    assert all(
        phrase in DOCUMENT_TOOL_DEF.description
        for phrase in ("页眉", "备注", "公式文本")
    )


def test_p7c_modules_do_not_duplicate_unicode_sanitization() -> None:
    for path in (
        Path("src/tools/document_tools.py"),
        Path("src/tools/search_tools.py"),
        Path("src/core/result_reflow.py"),
    ):
        assert "unicodedata" not in path.read_text(encoding="utf-8")
