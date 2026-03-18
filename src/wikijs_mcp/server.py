"""Wiki.js MCP server entry point.

Starts a FastMCP server with streamable HTTP transport. All inbound requests
are authenticated via a static bearer token (MCP_API_KEY env var) before they
reach any MCP handler.
"""

import hmac
import logging
import os
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


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests that do not carry the correct MCP API key."""

    def __init__(self, app, api_key: str) -> None:
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next) -> Response:
        # Allow health-check probe through without auth
        if request.url.path == "/health":
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

    client = WikiJSClient(base_url=wikijs_url, api_key=wikijs_api_key)
    logger.info("Connected to Wiki.js at %s", wikijs_url)

    yield {"client": client}

    logger.info("Shutting down wikijs_mcp")


# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

def _build_transport_security() -> TransportSecuritySettings:
    """Build transport security settings from environment.

    Set MCP_ALLOWED_HOSTS to a comma-separated list of allowed Host header values
    (supports wildcard ports via ':*', e.g. '192.168.1.72:*').
    Leave unset or empty to disable DNS rebinding protection (safe when the server
    is already protected by BearerAuthMiddleware on a private network).
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
# Health endpoint
# ---------------------------------------------------------------------------

@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> Response:
    return Response('{"status":"ok"}', media_type="application/json")


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
