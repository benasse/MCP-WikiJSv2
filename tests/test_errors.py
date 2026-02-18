"""Tests for _handle_api_error and WikiJSError."""

import httpx
import pytest

from wikijs_mcp.errors import WikiJSError, _handle_api_error


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "http://wiki.example.com/graphql")
    resp = httpx.Response(status_code=status_code, request=req)
    return httpx.HTTPStatusError("error", request=req, response=resp)


def test_wikijs_error_message():
    result = _handle_api_error(WikiJSError("page not found"))
    assert result.startswith("Error:")
    assert "page not found" in result


def test_http_401():
    result = _handle_api_error(_http_error(401))
    assert "Unauthorized" in result
    assert "WIKIJS_API_KEY" in result


def test_http_403():
    result = _handle_api_error(_http_error(403))
    assert "Forbidden" in result


def test_http_404():
    result = _handle_api_error(_http_error(404))
    assert "not found" in result.lower()


def test_http_429():
    result = _handle_api_error(_http_error(429))
    assert "Rate limit" in result


def test_http_500():
    result = _handle_api_error(_http_error(500))
    assert "HTTP 500" in result


def test_timeout_error():
    result = _handle_api_error(httpx.TimeoutException("timed out"))
    assert "timed out" in result.lower()
    assert "WIKIJS_URL" in result


def test_connect_error():
    result = _handle_api_error(httpx.ConnectError("connection refused"))
    assert "connect" in result.lower()
    assert "WIKIJS_URL" in result


def test_unexpected_error():
    result = _handle_api_error(ValueError("something weird"))
    assert "Unexpected error" in result
    assert "ValueError" in result


def test_all_error_strings_start_with_error_prefix():
    """Every mapped exception should return a string beginning with 'Error:'."""
    cases = [
        WikiJSError("x"),
        _http_error(401),
        _http_error(403),
        _http_error(404),
        _http_error(429),
        _http_error(500),
        httpx.TimeoutException("t"),
        httpx.ConnectError("c"),
        RuntimeError("unexpected"),
    ]
    for exc in cases:
        result = _handle_api_error(exc)
        assert result.startswith("Error:"), f"Failed for {type(exc).__name__}: {result!r}"
