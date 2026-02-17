"""Error types and handling utilities for the Wiki.js MCP server."""

import httpx


class WikiJSError(Exception):
    """Raised when the Wiki.js GraphQL API returns an error."""


def _handle_api_error(e: Exception) -> str:
    """Map exceptions to actionable error strings returned to the LLM client."""
    if isinstance(e, WikiJSError):
        return f"Error: Wiki.js API error — {e}"
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 401:
            return "Error: Unauthorized. Check that WIKIJS_API_KEY is valid and API access is enabled in Wiki.js admin."
        if status == 403:
            return "Error: Forbidden. The API key does not have permission for this operation."
        if status == 404:
            return "Error: Resource not found. Verify the page ID or path is correct."
        if status == 429:
            return "Error: Rate limit exceeded. Please wait before retrying."
        return f"Error: Wiki.js returned HTTP {status}."
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request to Wiki.js timed out. Check that Wiki.js is reachable at WIKIJS_URL."
    if isinstance(e, httpx.ConnectError):
        return "Error: Could not connect to Wiki.js. Check that WIKIJS_URL is correct and Wiki.js is running."
    return f"Error: Unexpected error — {type(e).__name__}: {e}"
