"""scrypt password hashing."""

from src.passwords import hash_password, verify_password


def test_hash_then_verify():
    h = hash_password("correct horse battery")
    assert h.startswith("scrypt$")
    assert verify_password("correct horse battery", h)
    assert not verify_password("wrong", h)


def test_salt_differs_per_hash():
    assert hash_password("same") != hash_password("same")


def test_malformed_hash_is_rejected():
    assert not verify_password("x", "not-a-hash")
    assert not verify_password("x", "scrypt$1$2$3$bad$bad")
