from functools import lru_cache
from pathlib import Path
import unicodedata

from argon2 import PasswordHasher, Type, exceptions


_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19 * 1024,
    parallelism=1,
    type=Type.ID,
)
_BLOCKLIST_PATH = Path(__file__).with_name("common_passwords.txt")


class PasswordPolicyError(ValueError):
    pass


def normalize_password(password: str) -> str:
    return unicodedata.normalize("NFC", password)


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    return frozenset(
        normalize_password(line.strip()).casefold()
        for line in _BLOCKLIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def validate_password(password: str) -> str:
    normalized = normalize_password(password)
    if not 15 <= len(normalized) <= 128:
        raise PasswordPolicyError("Password must contain 15 to 128 Unicode code points")
    if normalized.casefold() in _common_passwords():
        raise PasswordPolicyError("Choose a password that is not on the common-password blocklist")
    return normalized


def hash_password(password: str, *, enforce_policy: bool = True) -> str:
    normalized = validate_password(password) if enforce_policy else normalize_password(password)
    return _HASHER.hash(normalized)


def verify_password(password: str, encoded_hash: str) -> bool:
    normalized = normalize_password(password)
    try:
        return _HASHER.verify(encoded_hash, normalized)
    except (exceptions.VerifyMismatchError, exceptions.VerificationError, exceptions.InvalidHashError):
        return False


def password_needs_rehash(encoded_hash: str) -> bool:
    try:
        return _HASHER.check_needs_rehash(encoded_hash)
    except (exceptions.VerificationError, exceptions.InvalidHashError):
        return False

