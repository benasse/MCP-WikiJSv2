"""Tests for WikiJSClient (mocked httpx)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from wikijs_mcp.client import WikiJSClient
from wikijs_mcp.errors import WikiJSError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(data=None, errors=None, status_code=200):
    """Build a mock httpx.Response."""
    body = {}
    if data is not None:
        body["data"] = data
    if errors is not None:
        body["errors"] = errors

    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body

    if status_code >= 400:
        req = httpx.Request("POST", "http://wiki.example.com/graphql")
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=req, response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def _patch_http(response):
    """Patch httpx.AsyncClient so post() returns *response*."""
    mock_aclient = AsyncMock()
    mock_aclient.post = AsyncMock(return_value=response)
    mock_aclient.__aenter__ = AsyncMock(return_value=mock_aclient)
    mock_aclient.__aexit__ = AsyncMock(return_value=False)
    return patch("httpx.AsyncClient", return_value=mock_aclient)


@pytest.fixture
def client():
    return WikiJSClient("http://wiki.example.com", "test-api-key")


# ---------------------------------------------------------------------------
# query()
# ---------------------------------------------------------------------------

async def test_query_returns_data_dict(client):
    resp = _make_response(data={"pages": {"list": [{"id": 1}]}})
    with _patch_http(resp):
        result = await client.query("query { pages { list { id } } }")
    assert result == {"pages": {"list": [{"id": 1}]}}


async def test_query_raises_wikijserror_on_gql_errors(client):
    resp = _make_response(errors=[{"message": "Field 'bad' not found"}])
    with _patch_http(resp):
        with pytest.raises(WikiJSError, match="Field 'bad' not found"):
            await client.query("query { bad }")


async def test_query_raises_on_http_4xx(client):
    resp = _make_response(status_code=401)
    with _patch_http(resp):
        with pytest.raises(httpx.HTTPStatusError):
            await client.query("query { pages { list { id } } }")


async def test_query_sends_correct_url_and_payload(client):
    resp = _make_response(data={})
    mock_aclient = AsyncMock()
    mock_aclient.post = AsyncMock(return_value=resp)
    mock_aclient.__aenter__ = AsyncMock(return_value=mock_aclient)
    mock_aclient.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_aclient) as mock_cls:
        await client.query("query { test }", {"var": "value"})

    mock_aclient.post.assert_called_once()
    call_args = mock_aclient.post.call_args
    assert call_args.args[0] == "http://wiki.example.com/graphql"
    assert call_args.kwargs["json"] == {
        "query": "query { test }",
        "variables": {"var": "value"},
    }
    # Auth header passed to the client constructor
    constructor_kwargs = mock_cls.call_args.kwargs
    assert constructor_kwargs["headers"]["Authorization"] == "Bearer test-api-key"


async def test_query_omits_variables_when_none(client):
    resp = _make_response(data={})
    mock_aclient = AsyncMock()
    mock_aclient.post = AsyncMock(return_value=resp)
    mock_aclient.__aenter__ = AsyncMock(return_value=mock_aclient)
    mock_aclient.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_aclient):
        await client.query("query { test }")

    payload = mock_aclient.post.call_args.kwargs["json"]
    assert "variables" not in payload


async def test_query_combines_multiple_gql_errors(client):
    resp = _make_response(errors=[{"message": "Err1"}, {"message": "Err2"}])
    with _patch_http(resp):
        with pytest.raises(WikiJSError, match="Err1.*Err2"):
            await client.query("query { x }")


# ---------------------------------------------------------------------------
# mutate()
# ---------------------------------------------------------------------------

async def test_mutate_returns_data_on_success(client):
    data = {
        "pages": {
            "create": {
                "responseResult": {"succeeded": True, "message": "OK", "errorCode": None},
                "page": {"id": 42, "path": "test/page"},
            }
        }
    }
    resp = _make_response(data=data)
    with _patch_http(resp):
        result = await client.mutate("mutation { pages { create { responseResult { succeeded } page { id } } } }")
    assert result["pages"]["create"]["page"]["id"] == 42


async def test_mutate_raises_wikijserror_when_succeeded_false(client):
    data = {
        "pages": {
            "create": {
                "responseResult": {
                    "succeeded": False,
                    "message": "Path already exists",
                    "errorCode": 3001,
                },
                "page": None,
            }
        }
    }
    resp = _make_response(data=data)
    with _patch_http(resp):
        with pytest.raises(WikiJSError, match="Path already exists"):
            await client.mutate("mutation { pages { create { responseResult { succeeded message errorCode } page { id } } } }")


async def test_mutate_uses_errorcode_when_no_message(client):
    data = {
        "pages": {
            "delete": {
                "responseResult": {
                    "succeeded": False,
                    "message": None,
                    "errorCode": 7002,
                },
            }
        }
    }
    resp = _make_response(data=data)
    with _patch_http(resp):
        with pytest.raises(WikiJSError, match="errorCode=7002"):
            await client.mutate("mutation { pages { delete { responseResult { succeeded message errorCode } } } }")


async def test_mutate_skips_responseresult_check_if_absent(client):
    """Payloads without responseResult should not raise."""
    data = {"other": {"someKey": "value"}}
    resp = _make_response(data=data)
    with _patch_http(resp):
        result = await client.mutate("mutation { other { someKey } }")
    assert result == {"other": {"someKey": "value"}}
