from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_token_round_trip() -> None:
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", hashed)
    token = create_access_token("42")
    assert decode_access_token(token)["sub"] == "42"
