"""Bearer-token auth dependency for memory-api.

Compares the Authorization header against MEMORY_API_TOKEN env var. If the
env var is not set at startup, every authenticated endpoint returns 503 so
the service fails closed rather than running open. Public endpoints
(/healthz, /docs, /openapi.json) skip this dependency.
"""

import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def _expected_token() -> str:
    """Return the configured token, or empty string if unset."""
    return os.environ.get("MEMORY_API_TOKEN", "")


def require_bearer(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """FastAPI dependency: enforce bearer-token auth.

    Returns the validated token string on success. Raises 401 when the header
    is missing or the token does not match. Raises 503 when the server has
    no token configured (fail-closed).
    """
    expected = _expected_token()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MEMORY_API_TOKEN not configured on server",
        )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Constant-time compare to avoid timing oracles.
    if not secrets.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials
