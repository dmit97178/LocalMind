"""P5 memory-write sanitization behavior."""

from src.core.memory_hygiene import sanitize_for_memory, sanitize_memory_value


def test_sanitize_for_memory_replaces_secret_and_protected_path() -> None:
    text = "api_key=sk-live-secret stored in ~/.ssh/id_rsa"

    sanitized = sanitize_for_memory(text)

    assert "sk-live-secret" not in sanitized
    assert "~/.ssh/id_rsa" not in sanitized
    assert "[已脱敏:secret]" in sanitized
    assert sanitized == "api_key=[已脱敏:secret]"


def test_sanitize_for_memory_is_idempotent() -> None:
    sanitized = sanitize_for_memory("password=very-secret")

    assert sanitize_for_memory(sanitized) == sanitized


def test_sanitize_memory_value_recurses_through_structured_data() -> None:
    value = {
        "summary": "token=sk-live-secret",
        "items": ["~/.ssh/id_rsa", 42],
    }

    sanitized = sanitize_memory_value(value)

    assert sanitized == {
        "summary": "token=[已脱敏:secret]",
        "items": ["[已脱敏:path]", 42],
    }


def test_sanitize_for_memory_preserves_newlines_while_redacting_bare_secrets() -> None:
    sanitized = sanitize_for_memory("User: hello\nAssistant: sk-abcdefghijklmnopqrstuvwxyz")

    assert sanitized == "User: hello\nAssistant: [已脱敏:secret]"


def test_sanitize_for_memory_redacts_configured_protected_paths() -> None:
    sanitized = sanitize_for_memory(
        "review D:/private/secrets.txt", forbidden_paths=("D:/private",)
    )

    assert sanitized == "review [已脱敏:path]"
