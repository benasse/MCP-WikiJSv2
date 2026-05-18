"""Async GraphQL client for the Wiki.js v2 API."""

from typing import Any, Dict, Optional
import httpx
from .errors import WikiJSError

_GQL_ENDPOINT = "/graphql"
_TIMEOUT = 30.0


class WikiJSClient:
    """Thin async wrapper around the Wiki.js GraphQL API.

    A single instance is created at server startup and shared across all
    tool calls via the FastMCP lifespan mechanism.
    """

    def __init__(self, base_url: str, api_key: str, verify_ssl: bool = True) -> None:
        self._url = base_url.rstrip("/") + _GQL_ENDPOINT
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._verify_ssl = verify_ssl

    async def query(
        self, gql: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a GraphQL query and return the ``data`` dict.

        Raises:
            WikiJSError: When the response contains GraphQL-level errors.
            httpx.HTTPStatusError: On non-2xx HTTP responses.
            httpx.TimeoutException: When the request exceeds the timeout.
            httpx.ConnectError: When Wiki.js is unreachable.
        """
        return await self._execute(gql, variables)

    async def mutate(
        self, gql: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a GraphQL mutation and return the ``data`` dict.

        Additionally checks that the Wiki.js ``responseResult.succeeded`` flag
        is true for the first top-level mutation result encountered.

        Raises:
            WikiJSError: On GraphQL errors or ``succeeded == false``.
            httpx.HTTPStatusError: On non-2xx HTTP responses.
        """
        data = await self._execute(gql, variables)
        # Walk data → namespace (e.g. "pages") → operation (e.g. "create") → responseResult
        for _namespace, namespace_payload in data.items():
            if isinstance(namespace_payload, dict):
                for _op, op_payload in namespace_payload.items():
                    if isinstance(op_payload, dict) and "responseResult" in op_payload:
                        result = op_payload["responseResult"]
                        if not result.get("succeeded", False):
                            msg = result.get("message") or f"errorCode={result.get('errorCode')}"
                            raise WikiJSError(msg)
                    break
            break
        return data

    async def _execute(
        self, gql: str, variables: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"query": gql}
        if variables:
            payload["variables"] = variables

        async with httpx.AsyncClient(
            headers=self._headers,
            timeout=_TIMEOUT,
            verify=self._verify_ssl,
        ) as client:
            response = await client.post(self._url, json=payload)
            response.raise_for_status()

        body = response.json()
        if errors := body.get("errors"):
            messages = "; ".join(e.get("message", str(e)) for e in errors)
            raise WikiJSError(messages)

        return body.get("data", {})
