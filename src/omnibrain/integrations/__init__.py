"""OmniBrain integrations — external service connectors.

Available integrations:
    gmail       — GmailClient for fetching and searching emails
    calendar    — CalendarClient for fetching and searching events
    github      — (Phase 2)
"""


def _is_auth_error(error: Exception) -> bool:
    """Check if an API error is authentication-related.

    Shared helper used by GmailClient and CalendarClient.
    """
    error_str = str(error).lower()
    return any(indicator in error_str for indicator in [
        "invalid_grant",
        "token expired",
        "token has been expired",
        "401",
        "invalid credentials",
        "unauthorized",
    ])


from omnibrain.integrations.calendar import CalendarAuthError, CalendarClient  # noqa: E402
from omnibrain.integrations.gmail import GmailAuthError, GmailClient  # noqa: E402

__all__ = ["GmailClient", "GmailAuthError", "CalendarClient", "CalendarAuthError", "_is_auth_error"]
