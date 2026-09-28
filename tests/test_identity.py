"""P3 passphrase verification tests."""

from __future__ import annotations


def test_identity_verifier_sets_and_verifies_a_passphrase(tmp_path) -> None:
    from src.safety.identity import IdentityVerifier

    verifier = IdentityVerifier({"hash_file": str(tmp_path / "passphrase")})

    assert verifier.is_set is False
    assert verifier.verify("anything") is True
    verifier.set_passphrase("correct horse")
    assert verifier.is_set is True
    assert verifier.verify("wrong") is False
    assert verifier.verify("correct horse") is True


def test_identity_verifier_locks_after_configured_failures(tmp_path) -> None:
    from src.safety.identity import IdentityVerifier

    verifier = IdentityVerifier(
        {
            "hash_file": str(tmp_path / "passphrase"),
            "lockout_attempts": 2,
            "lockout_minutes": 10,
        }
    )
    verifier.set_passphrase("correct")

    assert verifier.verify("wrong") is False
    assert verifier.verify("wrong") is False
    assert verifier.locked_until() is not None
    assert verifier.verify("correct") is False


def test_identity_verifier_unlocks_after_lockout_expiry(tmp_path, monkeypatch) -> None:
    from src.safety import identity
    from src.safety.identity import IdentityVerifier

    current_time = 1_000.0
    monkeypatch.setattr(identity.time, "time", lambda: current_time)
    verifier = IdentityVerifier(
        {
            "hash_file": str(tmp_path / "passphrase"),
            "lockout_attempts": 1,
            "lockout_minutes": 1,
        }
    )
    verifier.set_passphrase("correct")

    assert verifier.verify("wrong") is False
    assert verifier.locked_until() == 1_060.0
    current_time = 1_061.0
    assert verifier.locked_until() is None
    assert verifier.verify("correct") is True


def test_identity_verifier_rejects_a_passphrase_file_deleted_after_setup(tmp_path) -> None:
    from src.core.schemas import LocalMindError
    from src.safety.identity import IdentityVerifier

    hash_file = tmp_path / "passphrase"
    verifier = IdentityVerifier({"hash_file": str(hash_file)})
    verifier.set_passphrase("correct")
    hash_file.unlink()

    assert verifier.is_set is True
    try:
        verifier.verify("correct")
    except LocalMindError as exc:
        assert exc.code == "CONFIG_ERROR"
    else:
        raise AssertionError("a removed passphrase file must not authorize execution")
