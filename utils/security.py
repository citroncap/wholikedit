"""Security utilities: machine-keyed encryption for OAuth token storage."""
from __future__ import annotations
import os
import base64
import secrets
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def _machine_fernet() -> Fernet:
    """Derive a stable Fernet key from machine-specific identifiers."""
    machine_id = (
        os.getenv("COMPUTERNAME", "localhost") +
        os.getenv("USERNAME", "user") +
        os.getenv("USERDOMAIN", "domain")
    )
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"wholikedit_v2_salt",
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))
    return Fernet(key)


_FERNET = _machine_fernet()


def encrypt_token(token: str) -> str:
    """Encrypt an OAuth token for local storage."""
    return _FERNET.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a stored OAuth token. Raises on tamper/key mismatch."""
    return _FERNET.decrypt(encrypted.encode()).decode()


def generate_room_code(length: int = 6) -> str:
    """Generate a random alphanumeric room code (unambiguous charset)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_player_id() -> str:
    """Generate a session-scoped player UUID."""
    import uuid
    return str(uuid.uuid4())


def generate_state_token() -> str:
    """CSRF state token for OAuth flow."""
    return secrets.token_urlsafe(24)
