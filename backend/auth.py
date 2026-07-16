"""
backend/auth.py — Pluggable JWT authentication for production deployment.

Supports any OIDC-compliant identity provider (AWS Cognito, Auth0, Okta, etc.)
by fetching the provider's JWKS (JSON Web Key Set) and verifying tokens against it.

Toggled via REQUIRE_AUTH env var:
  - REQUIRE_AUTH=true  → all protected routes require a valid Bearer token
  - REQUIRE_AUTH=false → authentication is skipped (local development default)

Environment variables:
  REQUIRE_AUTH  — "true" to enforce JWT verification (default: "false")
  JWKS_URI      — JWKS endpoint URL (e.g. https://cognito-idp.ap-south-1.amazonaws.com/POOL_ID/.well-known/jwks.json)
  JWT_AUDIENCE  — expected 'aud' claim (your app's client ID)
  JWT_ISSUER    — expected 'iss' claim (e.g. https://cognito-idp.ap-south-1.amazonaws.com/POOL_ID)
"""

import os
import time
import json
from typing import Optional

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# ── Configuration ─────────────────────────────────────────────────────────────
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"
JWKS_URI     = os.getenv("JWKS_URI", "")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "")
JWT_ISSUER   = os.getenv("JWT_ISSUER", "")

# ── JWKS cache (refreshed every 6 hours or on key miss) ──────────────────────
_jwks_cache: dict = {}
_jwks_fetched_at: float = 0.0
JWKS_TTL = 6 * 3600  # 6 hours


def _fetch_jwks() -> dict:
    """Fetch the JWKS from the identity provider and cache it."""
    global _jwks_cache, _jwks_fetched_at
    if not JWKS_URI:
        return {}
    try:
        resp = httpx.get(JWKS_URI, timeout=10)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
        _jwks_cache = {k["kid"]: k for k in keys if "kid" in k}
        _jwks_fetched_at = time.time()
    except Exception as e:
        print(f"[auth] WARNING: failed to fetch JWKS from {JWKS_URI}: {e}")
    return _jwks_cache


def _get_signing_key(kid: str) -> Optional[dict]:
    """Get a signing key by key ID, refreshing the cache if needed."""
    now = time.time()
    # Use cache if fresh
    if _jwks_cache and (now - _jwks_fetched_at) < JWKS_TTL and kid in _jwks_cache:
        return _jwks_cache[kid]
    # Refresh and try again
    refreshed = _fetch_jwks()
    return refreshed.get(kid)


def _decode_token(token: str) -> dict:
    """Decode and verify a JWT token against the provider's JWKS."""
    try:
        # Read the unverified header to get the key ID
        unverified_header = jwt.get_unverified_header(token)
    except jwt.DecodeError:
        raise HTTPException(status_code=401, detail="Invalid token format")

    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Token missing 'kid' header")

    key_data = _get_signing_key(kid)
    if not key_data:
        raise HTTPException(status_code=401, detail=f"Unknown signing key: {kid}")

    # Build the public key from JWKS
    try:
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
    except Exception:
        raise HTTPException(status_code=401, detail="Failed to construct public key from JWKS")

    # Decode and verify
    decode_options = {}
    decode_kwargs = {
        "algorithms": [unverified_header.get("alg", "RS256")],
        "options": decode_options,
    }
    if JWT_AUDIENCE:
        decode_kwargs["audience"] = JWT_AUDIENCE
    else:
        decode_options["verify_aud"] = False
    if JWT_ISSUER:
        decode_kwargs["issuer"] = JWT_ISSUER

    try:
        payload = jwt.decode(token, public_key, **decode_kwargs)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=401, detail="Invalid token audience")
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=401, detail="Invalid token issuer")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    return payload


# ── FastAPI security scheme ──────────────────────────────────────────────────
_bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser:
    """Represents a verified user extracted from a JWT token."""
    def __init__(self, sub: str, email: str = "", org_id: str = "", raw: dict = None):
        self.sub = sub          # unique user identifier
        self.email = email
        self.org_id = org_id
        self.raw = raw or {}    # full decoded JWT payload

    def __repr__(self):
        return f"AuthenticatedUser(sub={self.sub!r}, email={self.email!r}, org_id={self.org_id!r})"


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[AuthenticatedUser]:
    """
    FastAPI dependency for route-level authentication.

    When REQUIRE_AUTH=false (default, local dev):
      Returns None — routes work without any token.

    When REQUIRE_AUTH=true (production):
      Extracts the Bearer token, verifies it against the JWKS, and returns
      an AuthenticatedUser. Returns 401 if the token is missing or invalid.
    """
    if not REQUIRE_AUTH:
        return None

    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = _decode_token(credentials.credentials)

    return AuthenticatedUser(
        sub=payload.get("sub", ""),
        email=payload.get("email", payload.get("cognito:username", "")),
        org_id=payload.get("custom:org_id", payload.get("org_id", "")),
        raw=payload,
    )

