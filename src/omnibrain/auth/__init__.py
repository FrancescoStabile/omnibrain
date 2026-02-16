"""OmniBrain — Authentication package.

Re-exports:
    GoogleOAuthManager, GoogleOAuthError
    OnboardingAnalyzer, OnboardingResult, InsightCard
"""

from omnibrain.auth.google_oauth import GoogleOAuthError, GoogleOAuthManager
from omnibrain.auth.onboarding import InsightCard, OnboardingAnalyzer, OnboardingResult

__all__ = [
    "GoogleOAuthManager",
    "GoogleOAuthError",
    "OnboardingAnalyzer",
    "OnboardingResult",
    "InsightCard",
]
