"""Deterministic dangling-reference guard tests."""

from __future__ import annotations

import inspect
import re

from src.core.reference_guard import (
    _EXTERNAL_OBJECT_NOUNS,
    _NON_REFERENTIAL_COMPOUNDS,
    _SELF_REFERENTIAL_NOUNS,
    ReferenceGuardResult,
    detect_unresolved_reference,
)


def test_dangling_demonstrative_np_is_triggered() -> None:
    result = detect_unresolved_reference("把那个服务发布上去。")

    assert result == ReferenceGuardResult(True, "none", "那个服务")


def test_self_referential_np_is_not_triggered() -> None:
    result = detect_unresolved_reference("把这段话翻译一下，它是什么意思。")

    assert result.triggered is False
    assert result.resolved_by == "self_referential"


def test_same_turn_antecedent_resolves() -> None:
    result = detect_unresolved_reference("刚才说的是支付服务，把那个服务发布上去。")

    assert result == ReferenceGuardResult(False, "same_turn", "")


def test_history_resolves() -> None:
    result = detect_unresolved_reference(
        "把那个服务发布上去。",
        relevant_history=["我们讨论过支付服务。"],
    )

    assert result == ReferenceGuardResult(False, "history", "")


def test_unrelated_history_does_not_resolve() -> None:
    result = detect_unresolved_reference(
        "把那个服务发布上去。",
        relevant_history=["今天讨论天气。"],
    )

    assert result == ReferenceGuardResult(True, "none", "那个服务")


def test_project_id_alone_does_not_resolve() -> None:
    result = detect_unresolved_reference(
        "把那个服务发布上去。",
        project_state={"project_id": "p-1"},
    )

    assert result.triggered is True


def test_substantive_project_state_resolves() -> None:
    result = detect_unresolved_reference(
        "把那个服务发布上去。",
        project_state={"summary": "目标是发布支付服务"},
    )

    assert result == ReferenceGuardResult(False, "project_state", "")


def test_filler_prefix_does_not_resolve() -> None:
    result = detect_unresolved_reference("明天再把那个服务发布上去。")

    assert result.triggered is True


def test_bare_pronoun_at_turn_start_is_triggered() -> None:
    result = detect_unresolved_reference("把它删掉。")

    assert result == ReferenceGuardResult(True, "none", "它")


def test_resolved_first_marker_can_resolve_later_pronoun() -> None:
    result = detect_unresolved_reference(
        "刚才说的是支付服务，把那个服务发布上去，然后把它删掉。"
    )

    assert result.triggered is False


def test_unresolved_first_marker_cannot_resolve_later_pronoun() -> None:
    result = detect_unresolved_reference("把那个服务发布上去，然后把它删掉。")

    assert result == ReferenceGuardResult(True, "none", "那个服务")


def test_first_and_second_person_pronouns_are_excluded() -> None:
    assert detect_unresolved_reference("把我们系统的数据迁移到新集群。").triggered is False


def test_topic_routing_reference_is_excluded() -> None:
    assert (
        detect_unresolved_reference("继续之前的话题：把检查清单列出来。").triggered
        is False
    )


def test_discourse_anaphora_without_context_is_triggered() -> None:
    result = detect_unresolved_reference("按上述执行。")

    assert result == ReferenceGuardResult(True, "none", "上述")


def test_unrecognized_center_noun_fails_open() -> None:
    assert detect_unresolved_reference("把那个什么来着发布上去。").triggered is False


def test_bare_demonstrative_without_center_noun_fails_open() -> None:
    assert detect_unresolved_reference("把那个删掉。").triggered is False


def test_window_boundary_finds_center_noun() -> None:
    result = detect_unresolved_reference("把那个刚部署好的服务发布上去。")

    assert result.triggered is True
    assert result.marker_text == "那个刚部署好的服务"


def test_marker_text_is_first_unresolved_marker() -> None:
    result = detect_unresolved_reference("把那个服务发布上去，然后把它删掉。")

    assert result.marker_text == "那个服务"


def test_detector_accepts_no_model_derived_input() -> None:
    signature = inspect.signature(detect_unresolved_reference)
    rendered = str(signature)

    forbidden = {
        "candidate",
        "entities",
        "missing_info",
        "final_state",
        "risk_draft",
        "suggested_tools",
        "consultation_proposal",
        "IntentCandidate",
    }
    assert forbidden.isdisjoint(signature.parameters)
    assert "project_state" in signature.parameters
    for name in forbidden | {"state"}:
        assert re.search(rf"\b{re.escape(name)}\b", rendered) is None


def test_reference_noun_sets_are_disjoint() -> None:
    assert _SELF_REFERENTIAL_NOUNS.isdisjoint(_EXTERNAL_OBJECT_NOUNS)


def test_resolved_by_values_are_closed() -> None:
    results = (
        detect_unresolved_reference("普通输入"),
        detect_unresolved_reference("把这段话翻译一下。"),
        detect_unresolved_reference("支付服务就是目标，把那个服务发布上去。"),
        detect_unresolved_reference("把那个服务发布上去。", relevant_history=["支付服务"]),
        detect_unresolved_reference(
            "把那个服务发布上去。", project_state={"summary": "支付服务"}
        ),
    )

    assert {result.resolved_by for result in results} <= {
        "none",
        "self_referential",
        "same_turn",
        "history",
        "project_state",
    }


def test_non_referential_compounds_never_trigger() -> None:
    for compound in _NON_REFERENTIAL_COMPOUNDS:
        assert detect_unresolved_reference(f"{compound}服务要重启。").triggered is False

    positional = detect_unresolved_reference("因此那个服务要重启。")
    assert positional.triggered is True
    assert positional.marker_text == "那个服务"


def test_center_noun_must_be_adjacent_or_after_first_de() -> None:
    adjacent = detect_unresolved_reference("那个服务发布上去。")
    modified = detect_unresolved_reference("那个刚部署好的服务发布上去。")
    different_np = detect_unresolved_reference("这项工作交给系统处理。")

    assert adjacent.triggered is True
    assert modified.triggered is True
    assert modified.marker_text == "那个刚部署好的服务"
    assert different_np.triggered is False


def test_compound_exclusion_also_applies_to_pronouns() -> None:
    for text in ("其他任务怎么处理。", "其它任务怎么处理。", "其他人呢？"):
        assert detect_unresolved_reference(text).triggered is False


def test_discourse_anaphora_uses_whole_turn_excluding_own_window() -> None:
    resolved = detect_unresolved_reference(
        "刚才说的是支付服务，把那个服务发布上去。"
    )
    assert resolved.triggered is False
    assert resolved.resolved_by == "same_turn"

    for text in (
        "上述配置需要复核。",
        "前面提到的 3 个用例。",
        "刚才说的是什么？",
        "上述是模型输出。",
    ):
        result = detect_unresolved_reference(text)
        assert result.triggered is True
    assert detect_unresolved_reference("上述是模型输出。").marker_text == "上述"
