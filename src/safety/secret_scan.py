"""Single deterministic source for credential detection and redaction."""

from __future__ import annotations

import re
from dataclasses import dataclass

SECRET_REDACTION_PLACEHOLDER = "[已脱敏:secret]"

_LABEL_FAMILIES = {
    "password": (
        "password",
        "passwd",
        "passphrase",
        "密码",
        "口令",
        "账号密码",
        "登录密码",
        "用户密码",
        "账户密码",
        "密码短语",
    ),
    "secret": (
        "secret",
        "api_key",
        "apikey",
        "private_key",
        "access_key",
        "密钥",
        "私钥",
        "访问密钥",
        "密钥串",
        "凭据",
        "凭证",
        "连接串",
    ),
    "token": ("token", "auth_token", "令牌", "访问令牌"),
}
CREDENTIAL_LABELS = frozenset(
    label for labels in _LABEL_FAMILIES.values() for label in labels
)
_NORMALIZED_LABEL = {
    label.casefold(): (label.casefold() if label.isascii() else family)
    for family, labels in _LABEL_FAMILIES.items()
    for label in labels
}
_LABEL_PATTERN = re.compile(
    "|".join(
        re.escape(label)
        for label in sorted(CREDENTIAL_LABELS, key=len, reverse=True)
    ),
    re.IGNORECASE,
)
_EXPLICIT_SEPARATOR = re.compile(r"\s*(?:等于|[=:：＝]|是|为)\s*")
_BARE_SECRET_PATTERN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{20,}|(?:ghp|github_pat)_[A-Za-z0-9_]{20,})\b"
    r"|\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
)


@dataclass(frozen=True)
class CredentialHit:
    """A replaceable credential occurrence in source text."""

    label: str
    normalized_label: str | None
    value: str
    state: str
    start: int
    end: int


def scan_credentials(text: str) -> tuple[CredentialHit, ...]:
    """Return non-overlapping credential values in deterministic source order."""

    if not isinstance(text, str) or not text:
        return ()
    placeholder_spans = [
        (match.start(), match.end())
        for match in re.finditer(re.escape(SECRET_REDACTION_PLACEHOLDER), text)
    ]
    hits = _scan_assigned_credentials(text, placeholder_spans)
    occupied = [(hit.start, hit.end) for hit in hits]
    for match in _BARE_SECRET_PATTERN.finditer(text):
        if _overlaps(match.start(), match.end(), occupied + placeholder_spans):
            continue
        hits.append(
            CredentialHit(
                label="",
                normalized_label=None,
                value=match.group(0),
                state="replaceable",
                start=match.start(),
                end=match.end(),
            )
        )
    return tuple(sorted(hits, key=lambda hit: (hit.start, hit.end)))


def redact_outbound(text: str) -> str:
    """Redact credentials before cloud egress without changing other text."""

    return _redact(text)


def redact_local(text: str) -> str:
    """Redact credentials before local persistence without changing structure."""

    return _redact(text)


def contains_credential(text: object) -> bool:
    """Return whether text contains an assigned or recognizable bare credential."""

    return isinstance(text, str) and bool(scan_credentials(text))


def _scan_assigned_credentials(
    text: str, placeholder_spans: list[tuple[int, int]]
) -> list[CredentialHit]:
    lines = text.splitlines(keepends=True)
    if not lines:
        lines = [text]
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)

    hits: list[CredentialHit] = []
    occupied: list[tuple[int, int]] = []
    for line_index, raw_line in enumerate(lines):
        line = raw_line.rstrip("\r\n")
        for match in _LABEL_PATTERN.finditer(line):
            absolute_label_start = offsets[line_index] + match.start()
            absolute_label_end = offsets[line_index] + match.end()
            if _overlaps(absolute_label_start, absolute_label_end, placeholder_spans):
                continue
            label = match.group(0)
            boundary = _credential_boundary(line, match.end(), label)
            if boundary is None:
                continue
            replacement_start, value_start = boundary
            value_end = len(line)
            value = line[value_start:value_end].strip()
            absolute_start = offsets[line_index] + replacement_start
            absolute_end = offsets[line_index] + value_end
            if not value:
                continuation = _next_nonempty_line(lines, offsets, line_index + 1)
                if continuation is None:
                    continue
                absolute_start, absolute_end, value = continuation
            if value == SECRET_REDACTION_PLACEHOLDER:
                continue
            if _overlaps(absolute_start, absolute_end, occupied):
                continue
            hit = CredentialHit(
                label=label,
                normalized_label=_NORMALIZED_LABEL[label.casefold()],
                value=value,
                state="replaceable",
                start=absolute_start,
                end=absolute_end,
            )
            hits.append(hit)
            occupied.append((absolute_start, absolute_end))
    return hits


def _credential_boundary(line: str, label_end: int, label: str) -> tuple[int, int] | None:
    after = line[label_end:]
    explicit = _EXPLICIT_SEPARATOR.match(after)
    if explicit is not None:
        return label_end + explicit.end(), label_end + explicit.end()
    if after and after[0] in " \t":
        value_start = label_end
        while value_start < len(line) and line[value_start] in " \t":
            value_start += 1
        return label_end, value_start
    if not after or after[0].isspace() or _is_cjk(after[0]):
        return None
    if _is_latin_label(label) and _is_latin_identifier_char(after[0]):
        return None
    return label_end, label_end


def _next_nonempty_line(
    lines: list[str], offsets: list[int], start_index: int
) -> tuple[int, int, str] | None:
    for index in range(start_index, len(lines)):
        content = lines[index].rstrip("\r\n")
        if not content.strip():
            continue
        leading = len(content) - len(content.lstrip())
        trailing = len(content.rstrip())
        return offsets[index] + leading, offsets[index] + trailing, content.strip()
    return None


def _redact(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    redacted = text
    for hit in reversed(scan_credentials(text)):
        redacted = redacted[: hit.start] + SECRET_REDACTION_PLACEHOLDER + redacted[hit.end :]
    return redacted


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < other_end and end > other_start for other_start, other_end in spans)


def _is_latin_label(label: str) -> bool:
    return all(ord(char) < 128 for char in label)


def _is_latin_identifier_char(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char == "_")


def _is_cjk(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
    )
