"""
EncryptedTextField — stores text encrypted at rest using Fernet
(symmetric AES-128-CBC + HMAC-SHA256).

Key resolution order:
1. settings.FIELD_ENCRYPTION_KEY  (explicit urlsafe-base64 Fernet key)
2. Derived from settings.SECRET_KEY via SHA-256  [DEV ONLY — insecure in prod]

Set FIELD_ENCRYPTION_KEY in production via the FIELD_ENCRYPTION_KEY env var.
Generate a new key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import base64
import hashlib
import logging

from django.db import models

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet, InvalidToken

    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CRYPTO_AVAILABLE = False
    logger.warning(
        "cryptography package not available — EncryptedTextField will store plaintext."
    )


def _get_fernet() -> "Fernet":
    from django.conf import settings

    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if not key:
        # Derive a stable key from SECRET_KEY for local development.
        logger.debug(
            "FIELD_ENCRYPTION_KEY not set — deriving dev key from SECRET_KEY. "
            "Set FIELD_ENCRYPTION_KEY explicitly in production."
        )
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


class EncryptedTextField(models.TextField):
    """
    TextField subclass that transparently encrypts data before persistence
    and decrypts it after retrieval.

    The raw value stored in the database is a Fernet token (base64-encoded
    string beginning with 'gAA'). Existing plaintext is returned unchanged
    on decrypt failure to aid migration scenarios — log a warning in that case.
    """

    description = "Text field encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256)"

    def get_prep_value(self, value: str | None) -> str | None:
        """Encrypt before saving to DB."""
        if not _CRYPTO_AVAILABLE or value is None or value == "":
            return value
        if not isinstance(value, str):
            value = str(value)
        return _get_fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value: str | None, expression, connection) -> str | None:
        """Decrypt after reading from DB."""
        if not _CRYPTO_AVAILABLE or value is None or value == "":
            return value
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except (InvalidToken, ValueError, Exception) as exc:
            logger.warning(
                "EncryptedTextField: failed to decrypt value — returning raw. "
                "Did the FIELD_ENCRYPTION_KEY change? Error: %s",
                exc,
            )
            return value

    def to_python(self, value):
        """Called during form validation / deserialization — pass through."""
        return value
