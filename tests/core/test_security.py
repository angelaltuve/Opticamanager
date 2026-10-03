from __future__ import annotations

import bcrypt
import pytest

from opticamanager.core.security import hash_password, verify_password


class TestHashPassword:
    def test_returns_string(self) -> None:
        """hash_password returns a non-empty string."""
        hashed = hash_password("test123")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_returns_bcrypt_hash(self) -> None:
        """Returned string is a valid bcrypt hash starting with $2b$."""
        hashed = hash_password("test123")
        assert hashed.startswith("$2b$")

    def test_differs_from_plaintext(self) -> None:
        """Hash is not equal to the original password."""
        password = "mi_password_segura"
        hashed = hash_password(password)
        assert hashed != password

    def test_salting_produces_different_hashes(self) -> None:
        """Two calls with the same password produce different hashes (salting)."""
        password = "misma_contraseña"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2

    def test_unicode_password(self) -> None:
        """Works with Unicode passwords including accented characters."""
        password = "contraseña_ñ_ü_ç_áéíóú"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_empty_string(self) -> None:
        """Empty string is a valid password input."""
        hashed = hash_password("")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_password_at_72_byte_limit(self) -> None:
        """Password at the 72-byte bcrypt limit works correctly."""
        password = "a" * 72
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_password_over_72_bytes_raises(self) -> None:
        """Passwords longer than 72 bytes raise ValueError from bcrypt."""
        password = "a" * 100
        with pytest.raises(ValueError, match="password cannot be longer than 72"):
            hash_password(password)


class TestVerifyPassword:
    def test_valid_password_returns_true(self) -> None:
        """verify_password returns True for the correct password."""
        password = "correct_password"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_invalid_password_returns_false(self) -> None:
        """verify_password returns False for the wrong password."""
        password = "real_password"
        hashed = hash_password(password)
        assert verify_password("wrong_password", hashed) is False

    def test_empty_string_fails(self) -> None:
        """Empty string does not match a real hash."""
        hashed = hash_password("some_password")
        assert verify_password("", hashed) is False

    def test_none_hash_raises(self) -> None:
        """Passing a non-hash string raises bcrypt error."""
        with pytest.raises((ValueError, TypeError)):
            verify_password("test", "not_a_bcrypt_hash")

    def test_same_hash_verify_multiple_times(self) -> None:
        """Same hash can be verified multiple times consistently."""
        password = "consistent_test"
        hashed = hash_password(password)
        for _ in range(3):
            assert verify_password(password, hashed) is True

    def test_verify_against_known_good_hash(self) -> None:
        """Can verify against a manually crafted bcrypt hash."""
        password = "hello_world"
        hashed = hash_password(password)
        assert bcrypt.checkpw(
            password.encode("utf-8"),
            hashed.encode("utf-8"),
        )


class TestIntegration:
    def test_hash_then_verify_round_trip(self) -> None:
        """Full round-trip: hash a password then verify it."""
        passwords = [
            "simple",
            "with space",
            "MIXED_CASE_123",
            "!@#$%^&*()",
            "a" * 50,
            "",
        ]
        for pwd in passwords:
            hashed = hash_password(pwd)
            assert verify_password(pwd, hashed) is True, f"Failed for password: {pwd!r}"
