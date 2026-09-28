"""Bounded dangling-reference detection without claiming general coreference support.

The noun sets deliberately cover only common task objects. Unrecognized forms fail
open. Self-referential nouns must refer only to the current language material;
external entities must never be added to that set.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_QUANTIFIERS = frozenset("个些份条台次种位件批段句篇张部组套项款则页")
_EXTERNAL_OBJECT_NOUNS = frozenset(
    {
        "服务",
        "服务器",
        "文件",
        "目录",
        "项目",
        "系统",
        "任务",
        "工具",
        "配置",
        "脚本",
        "接口",
        "文档",
        "数据库",
        "集群",
        "环境",
        "模块",
        "组件",
        "记录",
        "报告",
        "日志",
        "版本",
        "分支",
        "镜像",
        "证书",
        "密钥",
        "账号",
        "权限",
        "计划",
        "流程",
        "用例",
        "场景",
        "缓存",
        "队列",
    }
)
# Admit only nouns that can refer exclusively to the current language material.
# External entities such as content, descriptions, or problems do not belong here.
_SELF_REFERENTIAL_NOUNS = frozenset({"话", "文字", "文本", "句子", "段落", "意思", "表述"})
_ALL_REFERENCE_NOUNS = _EXTERNAL_OBJECT_NOUNS | _SELF_REFERENTIAL_NOUNS
_PROJECT_STATE_SUBSTANTIVE_KEYS = frozenset({"goal", "summary", "constraints", "topic_tags"})
_CENTER_WINDOW = 8

_DEMONSTRATIVE_RE = re.compile(r"[这那该此]")
_THIRD_PERSON_PRONOUNS = ("它们", "他们", "她们", "它", "他", "她")
_DISCOURSE_TERMS = (
    "上面提到的",
    "前面提到的",
    "之前提到的",
    "刚才说的",
    "上述",
    "前述",
)
_REFERENCE_MARKERS = frozenset((*_THIRD_PERSON_PRONOUNS, *_DISCOURSE_TERMS))
_PRONOUN_RE = re.compile("|".join(map(re.escape, _THIRD_PERSON_PRONOUNS)))
_TOPIC_ROUTING_TERMS = ("继续之前的话题", "继续上面说的话题", "继续前面的话题")
_NON_REFERENTIAL_COMPOUNDS = frozenset(
    {
        "因此",
        "如此",
        "为此",
        "据此",
        "从此",
        "以此",
        "就此",
        "特此",
        "至此",
        "那么",
        "这么",
        "怎么",
        "多么",
        "应该",
        "这里",
        "那里",
        "哪里",
        "这儿",
        "那儿",
        "哪儿",
        "这边",
        "那边",
        "哪边",
        "这时",
        "那时",
        "此时",
        "此刻",
        "其他",
        "其它",
    }
)


@dataclass(frozen=True)
class ReferenceGuardResult:
    """Deterministic verdict on whether this turn's task object is resolvable."""

    triggered: bool
    resolved_by: str = "none"
    marker_text: str = ""


@dataclass(frozen=True)
class _Marker:
    start: int
    end: int
    text: str
    candidates: frozenset[str]
    self_referential: bool = False
    kind: str = "M1"


def detect_unresolved_reference(
    input_text: str,
    *,
    relevant_history: Sequence[str] = (),
    project_state: Mapping[str, object] | None = None,
) -> ReferenceGuardResult:
    """Return the first unresolved reference marker in a bounded marker set."""

    if not isinstance(input_text, str) or not input_text:
        return ReferenceGuardResult(False)

    markers = _find_markers(input_text)
    first_resolution = "none"
    history_text = "\n".join(item for item in relevant_history if isinstance(item, str))
    project_text = _project_text(project_state)

    for marker in markers:
        if marker.self_referential:
            resolved_by = "self_referential"
        else:
            prefix = input_text[: marker.start]
            same_turn = _same_turn_text(input_text, marker)
            resolved_by = _resolve_source(
                marker.candidates,
                prefix,
                same_turn,
                history_text,
                project_text,
            )
        if resolved_by == "none":
            return ReferenceGuardResult(True, "none", marker.text)
        if first_resolution == "none":
            first_resolution = resolved_by

    return ReferenceGuardResult(False, first_resolution)


def _find_markers(text: str) -> list[_Marker]:
    spans: list[_Marker] = []
    excluded = _excluded_spans(text)

    for match in _DEMONSTRATIVE_RE.finditer(text):
        if _inside_any(match.start(), excluded):
            continue
        center_start = match.end()
        if center_start < len(text) and text[center_start] in _QUANTIFIERS:
            center_start += 1
        window = text[center_start : center_start + _CENTER_WINDOW]
        noun = _center_noun(window)
        if noun is None:
            continue
        noun_offset, noun_text = noun
        end = center_start + noun_offset + len(noun_text)
        spans.append(
            _Marker(
                match.start(),
                end,
                text[match.start() : end],
                frozenset({noun_text}),
                noun_text in _SELF_REFERENTIAL_NOUNS,
                "M1",
            )
        )

    for term in _DISCOURSE_TERMS:
        for match in re.finditer(re.escape(term), text):
            spans.append(
                _Marker(
                    match.start(),
                    match.end(),
                    term,
                    _ALL_REFERENCE_NOUNS,
                    kind="M4",
                )
            )

    for match in _PRONOUN_RE.finditer(text):
        if _inside_any(match.start(), excluded):
            continue
        spans.append(
            _Marker(
                match.start(),
                match.end(),
                match.group(0),
                _ALL_REFERENCE_NOUNS,
                kind="M3",
            )
        )

    spans.sort(key=lambda marker: (marker.start, -(marker.end - marker.start)))
    return _deduplicate_overlaps(spans)


def _center_noun(window: str) -> tuple[int, str] | None:
    positions = [0]
    first_de = window.find("的")
    if first_de >= 0:
        positions.append(first_de + 1)
    matches = [
        (position, noun)
        for position in positions
        for noun in _ALL_REFERENCE_NOUNS
        if window.startswith(noun, position)
    ]
    if not matches:
        return None
    return min(matches, key=lambda item: (item[0], -len(item[1])))


def _resolve_source(
    candidates: frozenset[str],
    prefix: str,
    same_turn: str,
    history: str,
    project: str,
) -> str:
    self_candidates = candidates & _SELF_REFERENTIAL_NOUNS
    if _contains_any(prefix, self_candidates):
        return "self_referential"
    if _contains_any(same_turn, candidates):
        return "same_turn"
    if _contains_any(history, candidates):
        return "history"
    if _contains_any(project, candidates):
        return "project_state"
    return "none"


def _project_text(project_state: Mapping[str, object] | None) -> str:
    if not project_state:
        return ""
    values: list[str] = []
    for key in _PROJECT_STATE_SUBSTANTIVE_KEYS:
        value = project_state.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (list, tuple)):
            values.extend(item for item in value if isinstance(item, str))
    return "\n".join(values)


def _contains_any(text: str, candidates: frozenset[str]) -> bool:
    return any(candidate in text for candidate in candidates)


def _same_turn_text(text: str, marker: _Marker) -> str:
    if marker.kind != "M4":
        return text[: marker.start]
    excluded_end = min(len(text), marker.end + _CENTER_WINDOW)
    return text[: marker.start] + text[excluded_end:]


def _excluded_spans(text: str) -> list[tuple[int, int]]:
    return [
        (match.start(), match.end())
        for term in (*_TOPIC_ROUTING_TERMS, *_NON_REFERENTIAL_COMPOUNDS)
        for match in re.finditer(re.escape(term), text)
    ]


def _inside_any(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in spans)


def _deduplicate_overlaps(markers: list[_Marker]) -> list[_Marker]:
    result: list[_Marker] = []
    for marker in markers:
        if result and marker.start < result[-1].end:
            continue
        result.append(marker)
    return result
