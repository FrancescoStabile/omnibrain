"""
Tests for GoogleOAuthManager (src/omnibrain/auth/google_oauth.py).

Covers:
    - Scope resolution (profile always included)
    - Auth URL generation (happy + missing credentials)
    - Code exchange (mocked HTTP)
    - Token persistence + permissions
    - Connection / disconnection checks
    - User info fetching (mocked HTTP)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from omnibrain.auth.google_oauth import (
    CALENDAR_SCOPES,
    GMAIL_SCOPES,
    PROFILE_SCOPES,
    GoogleOAuthError,
    GoogleOAuthManager,
    _resolve_scopes,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    """Ephemeral data directory with a valid client-credentials stub."""
    creds = {
        "installed": {
            "client_id": "test-client-id.apps.googleusercontent.com",
            "client_secret": "test-client-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    (tmp_path / "google_credentials.json").write_text(json.dumps(creds))
    return tmp_path


@pytest.fixture()
def mgr(data_dir: Path) -> GoogleOAuthManager:
    return GoogleOAuthManager(data_dir)


# ═══════════════════════════════════════════════════════════════════════════
# Scope resolution
# ═══════════════════════════════════════════════════════════════════════════


class TestResolveScopes:
    def test_gmail_plus_calendar(self) -> None:
        scopes = _resolve_scopes("gmail+calendar")
        for s in GMAIL_SCOPES + CALENDAR_SCOPES + PROFILE_SCOPES:
            assert s in scopes

    def test_profile_always_included(self) -> None:
        scopes = _resolve_scopes("gmail")
        for s in PROFILE_SCOPES:
            assert s in scopes

    def test_unknown_group_ignored(self) -> None:
        scopes = _resolve_scopes("gmail+photos")
        assert len(scopes) == len(set(GMAIL_SCOPES + PROFILE_SCOPES))

    def test_empty_gives_profile_only(self) -> None:
        scopes = _resolve_scopes("")
        assert set(scopes) == set(PROFILE_SCOPES)

    def test_no_duplicates(self) -> None:
        scopes = _resolve_scopes("gmail+gmail+calendar")
        assert len(scopes) == len(set(scopes))


# ═══════════════════════════════════════════════════════════════════════════
# Connection / credentials checks
# ═══════════════════════════════════════════════════════════════════════════


class TestConnectionChecks:
    def test_has_client_credentials(self, mgr: GoogleOAuthManager) -> None:
        assert mgr.has_client_credentials() is True

    def test_no_client_credentials(self, tmp_path: Path) -> None:
        m = GoogleOAuthManager(tmp_path)
        assert m.has_client_credentials() is False

    def test_not_connected_initially(self, mgr: GoogleOAuthManager) -> None:
        assert mgr.is_connected() is False

    def test_connected_after_save(self, mgr: GoogleOAuthManager) -> None:
        mgr.save_tokens({"token": "abc", "refresh_token": "xyz"})
        assert mgr.is_connected() is True


# ═══════════════════════════════════════════════════════════════════════════
# Auth URL
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateAuthUrl:
    def test_returns_google_url(self, mgr: GoogleOAuthManager) -> None:
        url = mgr.create_auth_url(
            redirect_uri="http://localhost:7432/api/v1/oauth/google/callback",
        )
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
        assert "client_id=test-client-id" in url
        assert "redirect_uri=http" in url

    def test_state_param(self, mgr: GoogleOAuthManager) -> None:
        url = mgr.create_auth_url(
            redirect_uri="http://localhost:7432/callback",
            state="/onboarding",
        )
        assert "state=%2Fonboarding" in url

    def test_offline_access(self, mgr: GoogleOAuthManager) -> None:
        url = mgr.create_auth_url(redirect_uri="http://localhost/cb")
        assert "access_type=offline" in url

    def test_consent_prompt(self, mgr: GoogleOAuthManager) -> None:
        url = mgr.create_auth_url(redirect_uri="http://localhost/cb")
        assert "prompt=consent" in url

    def test_missing_credentials_raises(self, tmp_path: Path) -> None:
        m = GoogleOAuthManager(tmp_path)
        with pytest.raises(GoogleOAuthError, match="not found"):
            m.create_auth_url(redirect_uri="http://localhost/cb")

    def test_bad_credentials_json(self, data_dir: Path) -> None:
        (data_dir / "google_credentials.json").write_text('{"bad": true}')
        m = GoogleOAuthManager(data_dir)
        with pytest.raises(GoogleOAuthError, match="missing"):
            m.create_auth_url(redirect_uri="http://localhost/cb")


# ═══════════════════════════════════════════════════════════════════════════
# Token persistence
# ═══════════════════════════════════════════════════════════════════════════


class TestSaveTokens:
    def test_creates_file(self, mgr: GoogleOAuthManager, data_dir: Path) -> None:
        mgr.save_tokens({"token": "access123", "refresh_token": "refresh456"})
        assert (data_dir / "google_token.json").exists()

    def test_file_contents(self, mgr: GoogleOAuthManager, data_dir: Path) -> None:
        tok = {"token": "a", "refresh_token": "b", "extra": "c"}
        mgr.save_tokens(tok)
        loaded = json.loads((data_dir / "google_token.json").read_text())
        assert loaded["token"] == "a"
        assert loaded["refresh_token"] == "b"
        assert loaded["extra"] == "c"

    def test_secure_permissions(self, mgr: GoogleOAuthManager, data_dir: Path) -> None:
        mgr.save_tokens({"token": "t"})
        stat = os.stat(data_dir / "google_token.json")
        mode = oct(stat.st_mode)[-3:]
        assert mode == "600"

    def test_creates_data_dir(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b"
        m = GoogleOAuthManager(deep)
        m.save_tokens({"token": "t"})
        assert (deep / "google_token.json").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Disconnect
# ═══════════════════════════════════════════════════════════════════════════


class TestDisconnect:
    def test_disconnect_returns_false_when_no_token(self, mgr: GoogleOAuthManager) -> None:
        assert mgr.disconnect() is False

    def test_disconnect_removes_token(self, mgr: GoogleOAuthManager, data_dir: Path) -> None:
        mgr.save_tokens({"token": "t"})
        assert mgr.is_connected()
        assert mgr.disconnect() is True
        assert not mgr.is_connected()
        assert not (data_dir / "google_token.json").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Exchange code (mocked)
# ═══════════════════════════════════════════════════════════════════════════


class TestExchangeCode:
    def test_successful_exchange(self, mgr: GoogleOAuthManager, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mock the HTTP call to Google's token endpoint."""
        import io
        import urllib.request

        fake_response = json.dumps({
            "access_token": "ya29.test",
            "refresh_token": "1//test-refresh",
            "token_type": "Bearer",
            "scope": "openid email profile https://www.googleapis.com/auth/gmail.readonly",
            "expires_in": 3600,
        }).encode()

        class FakeResp:
            def read(self) -> bytes:
                return fake_response

            def __enter__(self) -> "FakeResp":
                return self

            def __exit__(self, *a: object) -> None:
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())

        tokens = mgr.exchange_code("auth-code-123", "http://localhost/cb")
        assert tokens["token"] == "ya29.test"
        assert tokens["refresh_token"] == "1//test-refresh"
        assert tokens["client_id"] == "test-client-id.apps.googleusercontent.com"
        assert "gmail.readonly" in " ".join(tokens["scopes"])

    def test_google_error_raises(self, mgr: GoogleOAuthManager, monkeypatch: pytest.MonkeyPatch) -> None:
        import urllib.request

        error_resp = json.dumps({
            "error": "invalid_grant",
            "error_description": "Code was already redeemed.",
        }).encode()

        class FakeResp:
            def read(self) -> bytes:
                return error_resp

            def __enter__(self) -> "FakeResp":
                return self

            def __exit__(self, *a: object) -> None:
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())

        with pytest.raises(GoogleOAuthError, match="invalid_grant"):
            mgr.exchange_code("bad-code", "http://localhost/cb")

    def test_network_error_raises(self, mgr: GoogleOAuthManager, monkeypatch: pytest.MonkeyPatch) -> None:
        import urllib.request

        def raise_err(*a: object, **kw: object) -> None:
            raise OSError("Connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", raise_err)

        with pytest.raises(GoogleOAuthError, match="failed"):
            mgr.exchange_code("code", "http://localhost/cb")


# ═══════════════════════════════════════════════════════════════════════════
# User info (mocked HTTP)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetUserInfo:
    def test_returns_empty_when_not_connected(self, mgr: GoogleOAuthManager) -> None:
        assert mgr.get_user_info() == {}

    def test_returns_profile(self, mgr: GoogleOAuthManager, monkeypatch: pytest.MonkeyPatch) -> None:
        import urllib.request

        mgr.save_tokens({"token": "ya29.valid", "refresh_token": "r"})

        profile = json.dumps({
            "email": "user@example.com",
            "name": "Test User",
            "picture": "https://example.com/pic.jpg",
        }).encode()

        class FakeResp:
            def read(self) -> bytes:
                return profile

            def __enter__(self) -> "FakeResp":
                return self

            def __exit__(self, *a: object) -> None:
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())

        info = mgr.get_user_info()
        assert info["email"] == "user@example.com"
        assert info["name"] == "Test User"
        assert info["picture"] == "https://example.com/pic.jpg"

    def test_returns_empty_on_error(self, mgr: GoogleOAuthManager, monkeypatch: pytest.MonkeyPatch) -> None:
        import urllib.request

        mgr.save_tokens({"token": "ya29.valid"})

        def raise_err(*a: object, **kw: object) -> None:
            raise OSError("timeout")

        monkeypatch.setattr(urllib.request, "urlopen", raise_err)
        assert mgr.get_user_info() == {}


# ═══════════════════════════════════════════════════════════════════════════
# Web credentials format
# ═══════════════════════════════════════════════════════════════════════════


class TestWebClientFormat:
    """Ensure 'web' key in credentials.json is accepted (not just 'installed')."""

    def test_web_key(self, tmp_path: Path) -> None:
        creds = {
            "web": {
                "client_id": "web-client.apps.googleusercontent.com",
                "client_secret": "web-secret",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        (tmp_path / "google_credentials.json").write_text(json.dumps(creds))
        m = GoogleOAuthManager(tmp_path)
        url = m.create_auth_url(redirect_uri="http://localhost/cb")
        assert "client_id=web-client" in url
