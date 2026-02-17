"""OAuth routes for OmniBrain API."""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from omnibrain.interfaces.api_models import (
    OAuthDisconnectResponse,
    OAuthStatusResponse,
    OAuthUrlResponse,
)

logger = logging.getLogger("omnibrain.api")


def register_oauth_routes(app, server, verify_api_key) -> None:  # noqa: ANN001
    """Register Google OAuth routes."""

    @app.get("/api/v1/oauth/google", response_model=OAuthUrlResponse)
    async def oauth_google_start(
        scope: str = Query("gmail+calendar", description="Scope groups"),
        redirect: str = Query("", description="Frontend redirect after auth"),
        token: str = Depends(verify_api_key),
    ) -> OAuthUrlResponse:
        """Generate Google OAuth consent URL."""
        from omnibrain.auth.google_oauth import GoogleOAuthManager

        mgr = GoogleOAuthManager(server._data_dir)
        if not mgr.has_client_credentials():
            raise HTTPException(
                status_code=503,
                detail="Google OAuth not configured — google_credentials.json missing",
            )

        callback_url = f"http://{server._get_api_origin()}/api/v1/oauth/google/callback"
        state = redirect or ""
        auth_url = mgr.create_auth_url(
            redirect_uri=callback_url,
            scopes=scope,
            state=state,
        )
        return OAuthUrlResponse(auth_url=auth_url)

    @app.get("/api/v1/oauth/google/callback")
    async def oauth_google_callback(
        code: str = Query(..., description="Auth code from Google"),
        state: str = Query("", description="Original redirect URL"),
    ) -> RedirectResponse:
        """Handle Google OAuth callback — exchange code, save tokens."""
        from omnibrain.auth.google_oauth import GoogleOAuthError, GoogleOAuthManager

        mgr = GoogleOAuthManager(server._data_dir)
        callback_url = f"http://{server._get_api_origin()}/api/v1/oauth/google/callback"

        try:
            tokens = mgr.exchange_code(code, callback_url)
            mgr.save_tokens(tokens)
        except GoogleOAuthError as e:
            logger.error("OAuth callback failed: %s", e)
            err_base = state or ""
            if err_base and not err_base.startswith("http"):
                err_base = ""
            if err_base:
                err_sep = "&" if "?" in err_base else "?"
                err_url = f"{err_base}{err_sep}oauth=error&message={str(e)}"
            else:
                err_url = f"/?oauth=error&message={str(e)}"
            return RedirectResponse(url=err_url)

        # Broadcast to WS clients
        await server.broadcast("google_connected", {"email": mgr.get_user_info().get("email", "")})

        # state carries the frontend origin (e.g. http://localhost:3000)
        base = state or ""
        if base and not base.startswith("http"):
            base = ""
        if base:
            sep = "&" if "?" in base else "?"
            redirect_url = f"{base}{sep}oauth=success"
        else:
            redirect_url = "/?oauth=success"
        return RedirectResponse(url=redirect_url)

    @app.get("/api/v1/oauth/status", response_model=OAuthStatusResponse)
    async def oauth_status(
        token: str = Depends(verify_api_key),
    ) -> OAuthStatusResponse:
        """Check whether Google is connected."""
        from omnibrain.auth.google_oauth import GoogleOAuthManager

        mgr = GoogleOAuthManager(server._data_dir)
        if not mgr.is_connected():
            return OAuthStatusResponse(
                connected=False,
                has_client_credentials=mgr.has_client_credentials(),
            )
        info = mgr.get_user_info()
        return OAuthStatusResponse(
            connected=True,
            email=info.get("email", ""),
            name=info.get("name", ""),
            scopes=["gmail.readonly", "calendar.readonly"],
            has_client_credentials=True,
        )

    @app.post("/api/v1/oauth/disconnect", response_model=OAuthDisconnectResponse)
    async def oauth_disconnect(
        token: str = Depends(verify_api_key),
    ) -> OAuthDisconnectResponse:
        """Disconnect Google (remove stored token)."""
        from omnibrain.auth.google_oauth import GoogleOAuthManager

        mgr = GoogleOAuthManager(server._data_dir)
        removed = mgr.disconnect()
        if removed:
            await server.broadcast("google_disconnected")
        return OAuthDisconnectResponse(disconnected=removed)
