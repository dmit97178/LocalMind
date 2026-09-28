"""Local passphrase verification for sensitive operations."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.core.schemas import LocalMindError


@dataclass
class IdentityVerifier:
    """Verify a local passphrase and apply an in-memory failure lockout."""

    passphrase_config: dict
    _failed_attempts: int = field(default=0, init=False)
    _locked_until: float | None = field(default=None, init=False)
    _passphrase_configured: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        hash_file = self.passphrase_config.get("hash_file", "./data/.passphrase")
        attempts = self.passphrase_config.get("lockout_attempts", 5)
        minutes = self.passphrase_config.get("lockout_minutes", 10)
        if not isinstance(hash_file, str) or not hash_file:
            raise _config_error("safety.passphrase.hash_file must be a non-empty string")
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
            raise _config_error("safety.passphrase.lockout_attempts must be a positive integer")
        if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes < 1:
            raise _config_error("safety.passphrase.lockout_minutes must be a positive integer")
        self._hash_file = Path(hash_file)
        self._lockout_attempts = attempts
        self._lockout_seconds = minutes * 60
        self._passphrase_configured = self._hash_file.exists()
        if self._passphrase_configured:
            self._read_hash()

    @property
    def is_set(self) -> bool:
        return self._passphrase_configured

    def locked_until(self) -> float | None:
        """Return the active lockout expiry, clearing an expired lockout."""

        if self._locked_until is not None and time.time() >= self._locked_until:
            self._locked_until = None
            self._failed_attempts = 0
        return self._locked_until

    def set_passphrase(self, plaintext: str) -> None:
        """Persist an initial passphrase; replacement requires explicit future support."""

        if self.is_set:
            raise _config_error("A passphrase is already configured")
        if not isinstance(plaintext, str) or not plaintext:
            raise _config_error("Passphrase must be a non-empty string")
        salt = os.urandom(16)
        digest = _derive(plaintext, salt)
        try:
            self._hash_file.parent.mkdir(parents=True, exist_ok=True)
            self._hash_file.write_text(f"{salt.hex()}${digest.hex()}\n", encoding="ascii")
        except OSError as exc:
            raise _config_error(f"Unable to write passphrase file: {exc}") from exc
        self._passphrase_configured = True

    def verify(self, passphrase: str) -> bool:
        """Return whether the supplied passphrase is valid and not locked out."""

        if not self._passphrase_configured:
            return True
        if self.locked_until() is not None:
            return False
        salt, expected = self._read_hash()
        actual = _derive(passphrase, salt)
        if hmac.compare_digest(actual, expected):
            self._failed_attempts = 0
            return True
        self._failed_attempts += 1
        if self._failed_attempts >= self._lockout_attempts:
            self._locked_until = time.time() + self._lockout_seconds
        return False

    def _read_hash(self) -> tuple[bytes, bytes]:
        try:
            raw = self._hash_file.read_text(encoding="ascii").strip()
            salt_hex, digest_hex = raw.split("$", maxsplit=1)
            salt = bytes.fromhex(salt_hex)
            digest = bytes.fromhex(digest_hex)
        except (OSError, UnicodeError, ValueError) as exc:
            raise _config_error(f"Invalid passphrase file: {exc}") from exc
        if len(salt) != 16 or len(digest) != 32:
            raise _config_error("Invalid passphrase file format")
        return salt, digest


def _derive(plaintext: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", plaintext.encode("utf-8"), salt, 100_000)


def _config_error(message: str) -> LocalMindError:
    return LocalMindError(
        code="CONFIG_ERROR",
        message=message,
        user_message="系统配置有误，请检查。",
        recoverable=False,
    )
