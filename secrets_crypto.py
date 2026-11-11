"""
Encryption helpers for secrets stored in cfg.ini (mower PINs, MQTT password).

Encrypted values are stored in cfg.ini as ``enc:<token>`` (Fernet: AES-128-CBC + HMAC-SHA256).
The key is NEVER stored in cfg.ini. It is loaded from (in this order):

1. the environment variable ``GARDENA_SECRET_KEY`` (e.g. for Docker secrets), or
2. a key file (``GARDENA_KEY_FILE``, default: ``.gardena.key`` next to this module),
   created with permissions 0600.

Plaintext values (without the ``enc:`` prefix) are still accepted for backwards
compatibility, so existing configs keep working.

Usage to encrypt a secret (prompts without echo, so it never lands in the shell history):
    python secrets_crypto.py

Author: __ABu__
"""

import getpass
import logging
import os
import sys

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

ENC_PREFIX = "enc:"
KEY_ENV = "GARDENA_SECRET_KEY"
KEY_FILE_ENV = "GARDENA_KEY_FILE"
DEFAULT_KEY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".gardena.key"
)


class SecretError(Exception):
    """Raised when a secret cannot be decrypted or no key is available."""


def key_file_path():
    """Returns the path of the key file (overridable via GARDENA_KEY_FILE)."""
    return os.environ.get(KEY_FILE_ENV, DEFAULT_KEY_FILE)


def load_key(create=False):
    """
    Loads the encryption key from the environment or the key file.
    param create: If True and no key exists yet, a new key file (0600) is generated.
    returns: The key as bytes.
    raises SecretError: If no key is available and create is False.
    """
    env_key = os.environ.get(KEY_ENV)
    if env_key:
        return env_key.strip().encode()

    path = key_file_path()
    if os.path.exists(path):
        if os.stat(path).st_mode & 0o077:
            logger.warning(
                f"Key file {path} is readable by other users. Run: chmod 600 {path}"
            )
        with open(path, "rb") as f:
            return f.read().strip()

    if not create:
        raise SecretError(
            f"No encryption key found. Set {KEY_ENV} or provide the key file {path} "
            f"(create one with: python secrets_crypto.py)."
        )

    key = Fernet.generate_key()
    # O_EXCL: never overwrite an existing key (that would make all secrets unreadable)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    logger.info(f"Created new encryption key file {path}")
    return key


def is_encrypted(value):
    """Returns True if the value is an encrypted secret (``enc:`` prefix)."""
    return isinstance(value, str) and value.startswith(ENC_PREFIX)


def encrypt_secret(plaintext, key):
    """
    Encrypts a secret (e.g. a PIN) for storage in cfg.ini.
    returns: The encrypted value in the form ``enc:<token>``.
    """
    if not plaintext:
        raise ValueError("Secret must not be empty.")
    token = Fernet(key).encrypt(str(plaintext).encode()).decode()
    return ENC_PREFIX + token


def decrypt_secret(value, key=None):
    """
    Decrypts a value from cfg.ini. Plaintext values (no ``enc:`` prefix) are returned unchanged.
    param key: The key; loaded via load_key() if omitted.
    raises SecretError: On a wrong key or a corrupted value.
    """
    if not is_encrypted(value):
        return value
    if key is None:
        key = load_key()
    try:
        return Fernet(key).decrypt(value[len(ENC_PREFIX) :].encode()).decode()
    except (InvalidToken, ValueError):
        # 'from None' prevents leaking key material or tokens via the traceback
        raise SecretError(
            "Could not decrypt secret: wrong key or corrupted value."
        ) from None


def main():
    """CLI: prompts for a secret (hidden input) and prints its encrypted form for cfg.ini."""
    secret = getpass.getpass("Secret to encrypt (PIN or password, hidden input): ")
    if not secret:
        print("Aborted: empty input.", file=sys.stderr)
        return 1
    key = load_key(create=True)
    print(encrypt_secret(secret, key))
    location = (
        f"environment variable {KEY_ENV}"
        if os.environ.get(KEY_ENV)
        else key_file_path()
    )
    print(f"Key location: {location}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
