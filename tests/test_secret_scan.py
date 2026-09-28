from src.safety.secret_scan import (
    SECRET_REDACTION_PLACEHOLDER,
    contains_credential,
    redact_local,
    redact_outbound,
    scan_credentials,
)


def test_scans_chinese_credential_assignment() -> None:
    hits = scan_credentials("我的账号密码是123456")

    assert len(hits) == 1
    assert hits[0].label == "账号密码"
    assert hits[0].normalized_label == "password"
    assert hits[0].value == "123456"
    assert hits[0].state == "replaceable"


def test_redacts_all_supported_credential_boundaries() -> None:
    samples = {
        "密码：abc 123": "密码：[已脱敏:secret]",
        "密码是青山绿水": "密码是[已脱敏:secret]",
        "密码 abc123": "密码[已脱敏:secret]",
        "密码abc123": "密码[已脱敏:secret]",
        "password = two words": "password = [已脱敏:secret]",
        "密码是abc，青山绿水": "密码是[已脱敏:secret]",
    }

    for raw, expected in samples.items():
        assert redact_outbound(raw) == expected
        assert redact_local(raw) == expected
        assert contains_credential(raw) is True


def test_redacts_value_on_the_next_non_empty_line_once() -> None:
    raw = "密码：\n\nabc123\n保留这一行"

    assert redact_outbound(raw) == "密码：\n\n[已脱敏:secret]\n保留这一行"


def test_placeholder_is_immune_and_redaction_is_idempotent() -> None:
    raw = f"api_key={SECRET_REDACTION_PLACEHOLDER}"

    assert scan_credentials(raw) == ()
    assert redact_outbound(raw) == raw
    assert redact_outbound(redact_outbound(raw)) == raw


def test_does_not_match_non_field_uses() -> None:
    for text in ("计数器是123456", "密码学是什么", "密钥管理体系", "tokenizer", "api_keys"):
        assert scan_credentials(text) == ()
        assert redact_outbound(text) == text


def test_preserves_bare_secret_detection() -> None:
    secret = "sk-EVAL-FAKE-abcdefghijklmnopqrstuvwxyz"

    assert contains_credential(secret) is True
    assert redact_outbound(f"值为 {secret}") == "值为 [已脱敏:secret]"


def test_normalizes_chinese_labels_to_families_but_preserves_english_names() -> None:
    assert scan_credentials("访问令牌：abc")[0].normalized_label == "token"
    assert scan_credentials("api_key=abc")[0].normalized_label == "api_key"


def test_detects_credential_labels_inside_environment_variable_names() -> None:
    samples = (
        "DB_PASSWORD=hunter2",
        "MYSQL_ROOT_PASSWORD=青山绿水",
        "AWS_SECRET_ACCESS_KEY=abc123",
        "secret_token=abc123",
    )

    for raw in samples:
        assert contains_credential(raw) is True
        assert "abc123" not in redact_outbound(raw)
        assert "hunter2" not in redact_outbound(raw)
        assert "青山绿水" not in redact_outbound(raw)
