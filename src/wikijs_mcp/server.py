"""Wiki.js MCP server entry point.

Starts a FastMCP server with streamable HTTP transport. Requests to the MCP
endpoint are authenticated via a static bearer token (MCP_API_KEY env var).

Remote clients (non-localhost) receive proactive OAuth discovery from the
Claude Code SDK. The minimal OAuth 2.1 endpoints below satisfy that flow and
ultimately hand the client the MCP_API_KEY as its bearer token, after which
BearerAuthMiddleware validates every /mcp request as before.

SSL note: token exchange happens in plaintext over HTTP. On any network that
is not fully trusted, place an SSL-terminating proxy in front of this server.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .client import WikiJSClient
from .tools.pages import register_page_tools

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("wikijs_mcp")


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable '{name}' is not set.")
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# OAuth in-memory state (lost on restart — one-time re-auth required)
# ---------------------------------------------------------------------------

# client_id → {"redirect_uris": list[str]}
_oauth_clients: dict[str, dict] = {}

# auth_code → {"client_id", "redirect_uri", "code_challenge", "expires_at"}
_oauth_codes: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

# OAuth discovery and token paths are public by spec; everything else
# (including /mcp) requires the bearer token.
_AUTH_PUBLIC_PATHS = {"/health", "/register", "/authorize", "/token"}
_AUTH_PUBLIC_PREFIXES = ("/.well-known/",)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests that do not carry the correct MCP API key.

    OAuth discovery and token endpoints are exempt — they are handled by the
    custom OAuth routes and must be reachable without prior credentials.
    """

    def __init__(self, app, api_key: str) -> None:
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in _AUTH_PUBLIC_PATHS or any(path.startswith(p) for p in _AUTH_PUBLIC_PREFIXES):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return Response("Unauthorized", status_code=401)

        token = auth_header[len("Bearer "):]
        if not hmac.compare_digest(token.encode(), self._api_key.encode()):
            return Response("Unauthorized", status_code=401)

        return await call_next(request)


# ---------------------------------------------------------------------------
# Lifespan — shared WikiJSClient
# ---------------------------------------------------------------------------

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    wikijs_url = _require_env("WIKIJS_URL")
    wikijs_api_key = _require_env("WIKIJS_API_KEY")
    trust_invalid_certs = _env_bool("WIKIJS_TRUST_INVALID_CERTS")

    client = WikiJSClient(
        base_url=wikijs_url,
        api_key=wikijs_api_key,
        verify_ssl=not trust_invalid_certs,
    )
    logger.info("Connected to Wiki.js at %s", wikijs_url)
    if trust_invalid_certs:
        logger.warning("WIKIJS_TRUST_INVALID_CERTS is enabled; TLS certificate verification is disabled for Wiki.js")

    yield {"client": client}

    logger.info("Shutting down wikijs_mcp")


# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

def _build_transport_security() -> TransportSecuritySettings:
    """Build transport security settings from environment.

    Set MCP_ALLOWED_HOSTS to a comma-separated list of allowed Host header
    values (supports wildcard ports via ':*', e.g. 'myhost:*').
    Leave unset or empty to disable DNS rebinding protection (safe when the
    server is already protected by BearerAuthMiddleware on a private network).
    """
    raw = os.getenv("MCP_ALLOWED_HOSTS", "").strip()
    if not raw:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    allowed = [h.strip() for h in raw.split(",") if h.strip()]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed,
    )


mcp = FastMCP("wikijs_mcp", lifespan=app_lifespan, transport_security=_build_transport_security())
register_page_tools(mcp)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_response(data: dict, status: int = 200) -> Response:
    return Response(json.dumps(data), status_code=status, media_type="application/json")


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> Response:
    return Response('{"status":"ok"}', media_type="application/json")


# ---------------------------------------------------------------------------
# OAuth 2.1 endpoints
#
# Claude Code performs proactive OAuth discovery for non-localhost servers
# before sending any configured headers. These endpoints satisfy that flow:
#
#   1. /.well-known/oauth-authorization-server  →  AS metadata
#   2. /register                                →  dynamic client registration
#   3. /authorize                               →  auto-approve, redirect with code
#   4. /token                                   →  exchange code → MCP_API_KEY
#
# After step 4 the SDK holds MCP_API_KEY as its bearer token and all
# subsequent /mcp calls pass through BearerAuthMiddleware unchanged.
# Refresh token is also set to MCP_API_KEY so token renewal is stateless.
# ---------------------------------------------------------------------------

@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
async def oauth_as_metadata(request: Request) -> Response:
    """OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
    base = f"{request.url.scheme}://{request.url.netloc}"
    return _json_response({
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "registration_endpoint": f"{base}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    })


@mcp.custom_route("/register", methods=["POST"])
async def oauth_register(request: Request) -> Response:
    """Dynamic client registration (RFC 7591)."""
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "invalid_request"}, status=400)

    client_id = str(uuid.uuid4())
    redirect_uris = body.get("redirect_uris", [])
    _oauth_clients[client_id] = {"redirect_uris": redirect_uris}
    logger.info("OAuth client registered: %s", client_id)

    return _json_response({
        "client_id": client_id,
        "redirect_uris": redirect_uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }, status=201)


@mcp.custom_route("/authorize", methods=["GET"])
async def oauth_authorize(request: Request) -> Response:
    """Authorization endpoint — auto-approves all registered clients.

    Generates an auth code and immediately redirects to redirect_uri without
    any user interaction. The one-time browser redirect is handled silently
    by Claude Code.
    """
    client_id = request.query_params.get("client_id", "")
    redirect_uri = request.query_params.get("redirect_uri", "")
    code_challenge = request.query_params.get("code_challenge", "")
    state = request.query_params.get("state", "")

    if client_id not in _oauth_clients:
        return _json_response({"error": "unauthorized_client"}, status=400)
    if not redirect_uri or not code_challenge:
        return _json_response({"error": "invalid_request"}, status=400)

    code = secrets.token_urlsafe(32)
    _oauth_codes[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "expires_at": time.time() + 300,  # 5-minute window
    }

    sep = "&" if "?" in redirect_uri else "?"
    location = f"{redirect_uri}{sep}code={code}"
    if state:
        location += f"&state={state}"

    return Response(status_code=302, headers={"Location": location})


@mcp.custom_route("/token", methods=["POST"])
async def oauth_token(request: Request) -> Response:
    """Token endpoint — issues MCP_API_KEY as the bearer/refresh token.

    Supports authorization_code (with PKCE) and refresh_token grant types.
    The refresh token is always MCP_API_KEY, making renewal stateless across
    server restarts.
    """
    api_key = os.environ.get("MCP_API_KEY", "").strip()

    try:
        form = await request.form()
    except Exception:
        return _json_response({"error": "invalid_request"}, status=400)

    grant_type = form.get("grant_type", "")

    if grant_type == "authorization_code":
        code = form.get("code", "")
        code_verifier = form.get("code_verifier", "")

        entry = _oauth_codes.pop(code, None)
        if not entry:
            return _json_response({"error": "invalid_grant", "error_description": "unknown code"}, status=400)
        if entry["expires_at"] < time.time():
            return _json_response({"error": "invalid_grant", "error_description": "code expired"}, status=400)

        # Verify PKCE (S256): BASE64URL(SHA256(code_verifier)) == code_challenge
        digest = hashlib.sha256(code_verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        if not hmac.compare_digest(challenge, entry["code_challenge"]):
            return _json_response({"error": "invalid_grant", "error_description": "code_verifier mismatch"}, status=400)

    elif grant_type == "refresh_token":
        refresh_token = form.get("refresh_token", "")
        if not api_key or not hmac.compare_digest(refresh_token.encode(), api_key.encode()):
            return _json_response({"error": "invalid_grant", "error_description": "invalid refresh_token"}, status=400)

    else:
        return _json_response({"error": "unsupported_grant_type"}, status=400)

    return _json_response({
        "access_token": api_key,
        "refresh_token": api_key,
        "token_type": "bearer",
        "expires_in": 86400,
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp_api_key = _require_env("MCP_API_KEY")
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))

    logger.info("Starting wikijs_mcp on %s:%s", host, port)

    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuthMiddleware, api_key=mcp_api_key)

    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level=os.getenv("LOG_LEVEL", "info").lower())


if __name__ == "__main__":
    main()
