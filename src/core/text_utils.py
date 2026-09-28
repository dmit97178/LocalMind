"""Dependency-free text helpers shared by core and adapter layers."""

from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> set[str]:
    """Split mixed Chinese and ASCII text into comparable tokens."""

    tokens = {token.lower() for token in _WORD_RE.findall(text)}
    for cjk_run in _CJK_RE.findall(text):
        tokens.add(cjk_run)
        tokens.update(_char_ngrams(cjk_run, size=2))
    return tokens


def _char_ngrams(text: str, size: int) -> set[str]:
    if len(text) <= size:
        return {text}
    return {text[index : index + size] for index in range(len(text) - size + 1)}
