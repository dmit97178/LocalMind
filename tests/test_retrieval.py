"""Tests for shared keyword retrieval helpers."""

from src.memory.retrieval import detect_topic_relation, keyword_score, tokenize


def test_tokenize_handles_mixed_chinese_and_ascii_text() -> None:
    terms = tokenize("检查 Ollama 端口 11434")

    assert {"ollama", "11434", "端口", "检查"}.issubset(terms)


def test_keyword_score_includes_metadata_terms() -> None:
    score = keyword_score(
        {"ollama", "端口", "检查"},
        "User wants help",
        {"topic": "Ollama 端口检查", "session_id": "s1"},
    )

    assert score == 3.0


def test_detect_topic_relation_preserves_all_supported_categories() -> None:
    assert detect_topic_relation("换个话题，讨论索引", "ollama port") == "new_topic"
    assert detect_topic_relation("ollama port still fails", "ollama port") == "same_topic"
    assert detect_topic_relation("继续刚才那个问题", "ollama port") == "shift_with_reference"
    assert detect_topic_relation("帮我看看这个", "ollama port") == "ambiguous"
