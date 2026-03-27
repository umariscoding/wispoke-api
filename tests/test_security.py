"""
Tests for password hashing utilities.
"""

from app.core.security import get_password_hash, verify_password


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "MySecurePassword123!"
        hashed = get_password_hash(password)
        assert hashed != password
        assert verify_password(password, hashed) is True

    def test_wrong_password_fails(self):
        hashed = get_password_hash("correct-password")
        assert verify_password("wrong-password", hashed) is False

    def test_different_hashes_for_same_password(self):
        pw = "same-password"
        h1 = get_password_hash(pw)
        h2 = get_password_hash(pw)
        assert h1 != h2  # bcrypt uses random salt
        assert verify_password(pw, h1)
        assert verify_password(pw, h2)
