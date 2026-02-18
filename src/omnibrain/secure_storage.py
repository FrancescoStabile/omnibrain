"""
OmniBrain — Secure Storage

Encrypted key-value vault for sensitive data (API tokens, OAuth tokens).
Manifesto: "API keys and tokens encrypted at rest."

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256) with a key
derived from a machine-stable seed + optional user passphrase via PBKDF2.

Storage: ``~/.omnibrain/vault.enc`` — a single encrypted JSON blob.
The encryption key is derived at startup and held in memory only.

Fallback: If ``cryptography`` is not installed, operates in plaintext
mode with a warning — never silently fails.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("omnibrain.secure_storage")


# ═══════════════════════════════════════════════════════════════════════════
# Machine Identity
# ═══════════════════════════════════════════════════════════════════════════


def _get_machine_id() -> str:
    """Get a stable, per-machine identifier.

    Sources (in order of preference):
    1. /etc/machine-id (Linux — set at install time, never changes)
    2. Platform node (fallback — MAC address based)
    3. Random UUID stored in data dir (ultimate fallback)
    """
    # Linux machine-id
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            mid = Path(path).read_text().strip()
            if mid:
                return mid
        except (OSError, PermissionError):
            pass

    # macOS: IOPlatformUUID
    if platform.system() == "Darwin":
        try:
            import subprocess

            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
        except Exception:
            pass

    # Fallback: platform node (MAC-based, not ideal but stable)
    return str(uuid.getnode())


def _derive_key(machine_id: str, passphrase: str = "", salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive a Fernet key from machine ID + optional passphrase via PBKDF2.

    Returns (key, salt) — salt must be stored alongside the vault.
    """
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        if salt is None:
            salt = os.urandom(16)

        seed = f"{machine_id}:{passphrase}".encode()

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480_000,  # OWASP 2023 recommendation
        )
        raw_key = kdf.derive(seed)
        # Fernet requires url-safe base64 of 32 bytes
        fernet_key = base64.urlsafe_b64encode(raw_key)
        return fernet_key, salt

    except ImportError:
        # Fallback: simple HMAC-based derivation (no cryptography package)
        import hmac

        if salt is None:
            salt = os.urandom(16)
        seed = f"{machine_id}:{passphrase}".encode()
        raw = hmac.new(salt, seed, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw), salt


# ═══════════════════════════════════════════════════════════════════════════
# Secure Storage
# ═══════════════════════════════════════════════════════════════════════════


class SecureStorage:
    """Encrypted key-value storage for sensitive data.

    Usage::

        vault = SecureStorage(data_dir)
        vault.store("google_token", '{"access_token": "..."}')
        token = vault.retrieve("google_token")
        vault.delete("google_token")
        all_keys = vault.list_keys()

    The vault file (``vault.enc``) contains:
    - 16-byte salt (for key derivation)
    - Fernet-encrypted JSON blob of all key-value pairs

    Thread safety: reads are lock-free; writes are atomic (write-rename).
    """

    def __init__(self, data_dir: Path, passphrase: str = "") -> None:
        self._data_dir = data_dir
        self._vault_path = data_dir / "vault.enc"
        self._passphrase = passphrase
        self._fernet: Any = None
        self._crypto_available = False
        self._cache: dict[str, str] | None = None

        self._init_crypto()

    def _init_crypto(self) -> None:
        """Initialize encryption. Falls back to obfuscation if cryptography missing."""
        try:
            from cryptography.fernet import Fernet

            machine_id = _get_machine_id()

            if self._vault_path.exists():
                # Read salt from existing vault
                raw = self._vault_path.read_bytes()
                if len(raw) < 16:
                    logger.warning("Corrupt vault file — reinitializing")
                    salt = None
                else:
                    salt = raw[:16]
            else:
                salt = None

            key, salt = _derive_key(machine_id, self._passphrase, salt)
            self._fernet = Fernet(key)
            self._salt = salt
            self._crypto_available = True
            logger.debug("SecureStorage initialized with Fernet encryption")

        except ImportError:
            logger.warning(
                "cryptography package not installed — vault will use obfuscation only. "
                "Install with: pip install omnibrain[secure]"
            )
            self._crypto_available = False

    # ──────────────────────────────────────────────────────────
    # Internal I/O
    # ──────────────────────────────────────────────────────────

    def _read_vault(self) -> dict[str, str]:
        """Read and decrypt the vault. Returns empty dict if not found."""
        if self._cache is not None:
            return self._cache

        if not self._vault_path.exists():
            self._cache = {}
            return self._cache

        try:
            raw = self._vault_path.read_bytes()

            if self._crypto_available and self._fernet:
                # First 16 bytes are salt, rest is Fernet token
                if len(raw) <= 16:
                    self._cache = {}
                    return self._cache
                encrypted = raw[16:]
                decrypted = self._fernet.decrypt(encrypted)
                self._cache = json.loads(decrypted)
            else:
                # Obfuscation fallback: base64-encoded JSON
                self._cache = json.loads(base64.b64decode(raw))

        except Exception as e:
            logger.error(f"Failed to read vault: {e}")
            self._cache = {}

        return self._cache

    def _write_vault(self, data: dict[str, str]) -> None:
        """Encrypt and write the vault atomically."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._cache = data

        try:
            json_bytes = json.dumps(data).encode()

            if self._crypto_available and self._fernet:
                encrypted = self._fernet.encrypt(json_bytes)
                payload = self._salt + encrypted
            else:
                # Obfuscation fallback
                payload = base64.b64encode(json_bytes)

            # Atomic write: write to temp then rename
            tmp_path = self._vault_path.with_suffix(".tmp")
            tmp_path.write_bytes(payload)
            tmp_path.rename(self._vault_path)

            # Restrictive permissions (owner only)
            try:
                os.chmod(self._vault_path, 0o600)
            except OSError:
                pass

        except Exception as e:
            logger.error(f"Failed to write vault: {e}")

    # ──────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────

    def store(self, key: str, value: str) -> None:
        """Store a key-value pair in the encrypted vault."""
        data = self._read_vault()
        data[key] = value
        self._write_vault(data)
        logger.debug(f"Stored key '{key}' in vault")

    def retrieve(self, key: str) -> str | None:
        """Retrieve a value by key. Returns None if not found."""
        data = self._read_vault()
        return data.get(key)

    def delete(self, key: str) -> bool:
        """Delete a key from the vault. Returns True if it existed."""
        data = self._read_vault()
        if key not in data:
            return False
        del data[key]
        self._write_vault(data)
        logger.debug(f"Deleted key '{key}' from vault")
        return True

    def list_keys(self) -> list[str]:
        """List all keys in the vault (values are NOT exposed)."""
        return list(self._read_vault().keys())

    def has_key(self, key: str) -> bool:
        """Check if a key exists in the vault."""
        return key in self._read_vault()

    def clear(self) -> None:
        """Delete all entries from the vault."""
        self._write_vault({})
        logger.info("Vault cleared")

    @property
    def is_encrypted(self) -> bool:
        """Whether the vault is using real encryption (vs obfuscation)."""
        return self._crypto_available

    # ──────────────────────────────────────────────────────────
    # Migration helpers
    # ──────────────────────────────────────────────────────────

    def migrate_google_token(self, data_dir: Path) -> bool:
        """Migrate plaintext Google token to encrypted vault.

        Reads ``google_token.json`` from data_dir, stores it in the vault
        as ``google_oauth_token``, and removes the plaintext file.

        Returns True if migration occurred.
        """
        token_path = data_dir / "google_token.json"
        if not token_path.exists():
            return False

        try:
            token_data = token_path.read_text()
            # Validate it's valid JSON
            json.loads(token_data)

            self.store("google_oauth_token", token_data)

            # Remove plaintext file
            token_path.unlink()
            logger.info("Migrated Google OAuth token to encrypted vault")
            return True

        except Exception as e:
            logger.error(f"Failed to migrate Google token: {e}")
            return False

    def get_google_token(self) -> dict[str, Any] | None:
        """Retrieve Google OAuth token as a dict."""
        raw = self.retrieve("google_oauth_token")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                logger.error("Corrupt Google token in vault")
        return None

    def store_google_token(self, token_data: dict[str, Any]) -> None:
        """Store Google OAuth token dict in vault."""
        self.store("google_oauth_token", json.dumps(token_data))
