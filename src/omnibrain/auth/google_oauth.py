"""
OmniBrain — Google OAuth Manager

Server-side Google OAuth 2.0 flow that works via the Web UI.
Replaces the CLI-only ``setup_google.py`` with browser-based consent.

The flow:
    1.  ``create_auth_url()`` → returns a Google consent URL
    2.  User authorises in browser → Google redirects back with ``code``
    3.  ``exchange_code()`` → exchanges code for tokens
    4.  ``save_tokens()`` → persists to ``~/.omnibrain/google_token.json``

Config expects ``google_credentials.json`` (OAuth *client* secret
downloaded from Google Cloud Console) in the data directory.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("omnibrain.auth.google_oauth")

# ═══════════════════════════════════════════════════════════════════════════
# Scopes
# ═══════════════════════════════════════════════════════════════════════════

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]

CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# Minimal profile info so we can greet the user by name
PROFILE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

SCOPE_MAP: dict[str, list[str]] = {
    "gmail": GMAIL_SCOPES,
    "calendar": CALENDAR_SCOPES,
    "profile": PROFILE_SCOPES,
}


def _resolve_scopes(requested: str = "gmail+calendar") -> list[str]:
    """Turn a ``+``-separated string into a flat scope list."""
    scopes: list[str] = list(PROFILE_SCOPES)  # always include profile
    for part in requested.split("+"):
        part = part.strip().lower()
        if part in SCOPE_MAP:
            scopes.extend(SCOPE_MAP[part])
    return sorted(set(scopes))


# ═══════════════════════════════════════════════════════════════════════════
# OAuth Manager
# ═══════════════════════════════════════════════════════════════════════════


class GoogleOAuthError(Exception):
    """Any OAuth-related failure."""


class GoogleOAuthManager:
    """Manages Google OAuth 2.0 flow for browser-based onboarding.

    Usage::

        mgr = GoogleOAuthManager(data_dir=Path("~/.omnibrain"))

        # 1. Generate auth URL
        url = mgr.create_auth_url(
            redirect_uri="http://localhost:7432/api/v1/oauth/google/callback",
            scopes="gmail+calendar",
        )

        # 2. After Google redirects back with ?code=...
        tokens = mgr.exchange_code(code, redirect_uri)

        # 3. Persist
        mgr.save_tokens(tokens)
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._credentials_path = data_dir / "google_credentials.json"
        self._token_path = data_dir / "google_token.json"

    # ── Paths ──

    @property
    def credentials_path(self) -> Path:
        return self._credentials_path

    @property
    def token_path(self) -> Path:
        return self._token_path

    # ── Connection checks ──

    def has_client_credentials(self) -> bool:
        """Check whether a Google OAuth client-secret file is present."""
        return self._credentials_path.exists()

    def is_connected(self) -> bool:
        """Check whether we already hold a valid (possibly expired) token."""
        return self._token_path.exists()

    def _load_client_config(self) -> dict[str, Any]:
        """Load and validate ``google_credentials.json``."""
        if not self._credentials_path.exists():
            raise GoogleOAuthError(
                f"Google credentials not found at {self._credentials_path}. "
                "Download a Desktop OAuth client JSON from Google Cloud Console."
            )
        with open(self._credentials_path) as f:
            data = json.load(f)

        # Google provides two flavour keys
        for key in ("web", "installed"):
            if key in data:
                return data[key]
        raise GoogleOAuthError("Invalid google_credentials.json — missing 'web' or 'installed' key")

    # ── Step 1: Auth URL ──

    def create_auth_url(
        self,
        redirect_uri: str,
        scopes: str = "gmail+calendar",
        state: str = "",
    ) -> str:
        """Build the Google consent URL.

        Parameters
        ----------
        redirect_uri : str
            The URL Google will redirect to after consent (our callback endpoint).
        scopes : str
            ``+``-separated scope groups, e.g. ``"gmail+calendar"``.
        state : str
            Optional opaque state token for CSRF protection.

        Returns
        -------
        str
            The full Google consent URL.
        """
        client = self._load_client_config()
        resolved = _resolve_scopes(scopes)

        params = {
            "client_id": client["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(resolved),
            "access_type": "offline",
            "prompt": "consent",
        }
        if state:
            params["state"] = state

        from urllib.parse import urlencode
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    # ── Step 2: Exchange code ──

    def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange an authorisation code for access + refresh tokens.

        Parameters
        ----------
        code : str
            The ``code`` query-param from the callback.
        redirect_uri : str
            Must exactly match the one used in ``create_auth_url``.

        Returns
        -------
        dict
            Token payload: ``access_token``, ``refresh_token``, ``token_uri``,
            ``client_id``, ``client_secret``, ``scopes``.

        Raises
        ------
        GoogleOAuthError
            On any network or validation failure.
        """
        client = self._load_client_config()

        import urllib.request
        import urllib.parse

        payload = urllib.parse.urlencode({
            "code": code,
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }).encode()

        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                token_data = json.loads(resp.read())
        except Exception as e:
            raise GoogleOAuthError(f"Token exchange failed: {e}") from e

        if "error" in token_data:
            raise GoogleOAuthError(
                f"Google returned error: {token_data['error']} — {token_data.get('error_description', '')}"
            )

        # Build the canonical token structure google-auth expects
        return {
            "token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", ""),
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "scopes": token_data.get("scope", "").split(),
            "expiry": "",  # google-auth will refresh when needed
        }

    # ── Step 3: Persist ──

    def save_tokens(self, tokens: dict[str, Any]) -> None:
        """Write tokens to ``google_token.json`` with ``0o600`` permissions."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self._token_path, "w") as f:
            json.dump(tokens, f, indent=2)
        try:
            os.chmod(self._token_path, 0o600)
        except OSError:
            pass
        logger.info("Google OAuth tokens saved to %s", self._token_path)

    # ── Convenience: user info ──

    def get_user_info(self) -> dict[str, str]:
        """Fetch basic profile data using the stored token.

        Returns ``{"email": ..., "name": ..., "picture": ...}`` or empty
        dict on any failure.
        """
        if not self.is_connected():
            return {}

        try:
            with open(self._token_path) as f:
                tok = json.load(f)
            access = tok.get("token", "")
            if not access:
                return {}

            import urllib.request
            req = urllib.request.Request(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                info = json.loads(resp.read())
            return {
                "email": info.get("email", ""),
                "name": info.get("name", ""),
                "picture": info.get("picture", ""),
            }
        except Exception as e:
            logger.debug("Failed to fetch user info: %s", e)
            return {}

    # ── Disconnect ──

    def disconnect(self) -> bool:
        """Remove stored token. Returns True if a token existed."""
        if self._token_path.exists():
            self._token_path.unlink()
            logger.info("Google OAuth disconnected")
            return True
        return False
