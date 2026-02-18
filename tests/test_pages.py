"""Tests for page tool helpers and tool logic (mocked WikiJSClient)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from wikijs_mcp.errors import WikiJSError
from wikijs_mcp.models import ResponseFormat
from wikijs_mcp.tools.pages import (
    _page_full_to_md,
    _page_summary_to_md,
    _paginate,
    register_page_tools,
)


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

class CapturingMCP:
    """Minimal stand-in for FastMCP that captures registered tool closures."""

    def __init__(self):
        self.tools: dict = {}

    def tool(self, name: str, annotations: dict = None):
        def decorator(fn):
            self.tools[name] = fn
            return fn
        return decorator


def make_ctx(client):
    """Build a minimal mock MCP Context backed by *client*."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"client": client}
    return ctx


@pytest.fixture(scope="module")
def tools() -> dict:
    mcp = CapturingMCP()
    register_page_tools(mcp)
    return mcp.tools


@pytest.fixture
def mock_client() -> AsyncMock:
    return AsyncMock()


# ---------------------------------------------------------------------------
# _page_summary_to_md
# ---------------------------------------------------------------------------

class TestPageSummaryToMd:
    def _page(self, **overrides):
        base = {
            "id": 1, "title": "Home", "path": "home", "locale": "en",
            "description": "The home page",
            "createdAt": "2024-01-01T00:00:00Z", "updatedAt": "2024-06-01T00:00:00Z",
        }
        return {**base, **overrides}

    def test_heading_includes_title_and_id(self):
        result = _page_summary_to_md(self._page())
        assert "## Home (id: 1)" in result

    def test_path_formatted_as_code(self):
        result = _page_summary_to_md(self._page())
        assert "`home`" in result

    def test_description_included_when_present(self):
        result = _page_summary_to_md(self._page())
        assert "The home page" in result

    def test_description_omitted_when_none(self):
        result = _page_summary_to_md(self._page(description=None))
        assert "Description" not in result

    def test_description_omitted_when_empty_string(self):
        result = _page_summary_to_md(self._page(description=""))
        assert "Description" not in result

    def test_untitled_fallback(self):
        result = _page_summary_to_md(self._page(title=None))
        assert "(untitled)" in result

    def test_locale_present(self):
        result = _page_summary_to_md(self._page(locale="fr"))
        assert "fr" in result


# ---------------------------------------------------------------------------
# _page_full_to_md
# ---------------------------------------------------------------------------

class TestPageFullToMd:
    def _page(self, **overrides):
        base = {
            "id": 10, "title": "Guide", "path": "guides/install", "locale": "en",
            "editor": "markdown", "isPublished": True, "isPrivate": False,
            "tags": [{"tag": "devops"}, {"tag": "linux"}],
            "content": "# Guide\n\nFollow these steps.",
            "createdAt": "2024-01-01T00:00:00Z", "updatedAt": "2024-06-01T00:00:00Z",
        }
        return {**base, **overrides}

    def test_heading_h1(self):
        result = _page_full_to_md(self._page())
        assert "# Guide (id: 10)" in result

    def test_tags_listed(self):
        result = _page_full_to_md(self._page())
        assert "devops" in result
        assert "linux" in result

    def test_no_tags_shows_none(self):
        result = _page_full_to_md(self._page(tags=[]))
        assert "none" in result

    def test_null_tags_shows_none(self):
        result = _page_full_to_md(self._page(tags=None))
        assert "none" in result

    def test_content_included(self):
        result = _page_full_to_md(self._page())
        assert "Follow these steps." in result

    def test_published_and_private_shown(self):
        result = _page_full_to_md(self._page(isPublished=True, isPrivate=False))
        assert "True" in result
        assert "False" in result


# ---------------------------------------------------------------------------
# _paginate
# ---------------------------------------------------------------------------

class TestPaginate:
    def test_first_page(self):
        items = list(range(50))
        r = _paginate(items, limit=10, offset=0)
        assert r["total"] == 50
        assert r["count"] == 10
        assert r["offset"] == 0
        assert r["items"] == list(range(10))
        assert r["has_more"] is True
        assert r["next_offset"] == 10

    def test_middle_page(self):
        items = list(range(50))
        r = _paginate(items, limit=10, offset=10)
        assert r["items"] == list(range(10, 20))
        assert r["has_more"] is True
        assert r["next_offset"] == 20

    def test_last_page_partial(self):
        items = list(range(25))
        r = _paginate(items, limit=10, offset=20)
        assert r["count"] == 5
        assert r["has_more"] is False
        assert r["next_offset"] is None

    def test_exact_fit(self):
        items = list(range(20))
        r = _paginate(items, limit=20, offset=0)
        assert r["has_more"] is False
        assert r["next_offset"] is None

    def test_empty_collection(self):
        r = _paginate([], limit=10, offset=0)
        assert r["total"] == 0
        assert r["count"] == 0
        assert r["has_more"] is False

    def test_offset_beyond_end(self):
        items = list(range(5))
        r = _paginate(items, limit=10, offset=10)
        assert r["count"] == 0
        assert r["has_more"] is False


# ---------------------------------------------------------------------------
# wikijs_search_pages
# ---------------------------------------------------------------------------

class TestSearchPagesTool:
    async def test_json_results(self, tools, mock_client):
        mock_client.query.return_value = {
            "pages": {
                "search": {
                    "results": [
                        {"id": 1, "title": "Docker Setup", "path": "docker",
                         "description": "Container guide", "locale": "en"},
                    ],
                    "totalHits": 1,
                    "suggestions": [],
                }
            }
        }
        result = await tools["wikijs_search_pages"](ctx=make_ctx(mock_client), query="docker")
        data = json.loads(result)
        assert data["totalHits"] == 1
        assert data["results"][0]["title"] == "Docker Setup"

    async def test_markdown_results(self, tools, mock_client):
        mock_client.query.return_value = {
            "pages": {
                "search": {
                    "results": [
                        {"id": 1, "title": "Docker Setup", "path": "docker",
                         "description": "", "locale": "en"},
                    ],
                    "totalHits": 1,
                    "suggestions": [],
                }
            }
        }
        result = await tools["wikijs_search_pages"](
            ctx=make_ctx(mock_client), query="docker",
            response_format=ResponseFormat.MARKDOWN,
        )
        assert "# Search Results" in result
        assert "Docker Setup" in result

    async def test_no_results_with_suggestions(self, tools, mock_client):
        mock_client.query.return_value = {
            "pages": {
                "search": {
                    "results": [],
                    "totalHits": 0,
                    "suggestions": ["docker", "container"],
                }
            }
        }
        result = await tools["wikijs_search_pages"](ctx=make_ctx(mock_client), query="dockr")
        assert "No pages found" in result
        assert "docker" in result

    async def test_no_results_no_suggestions(self, tools, mock_client):
        mock_client.query.return_value = {
            "pages": {"search": {"results": [], "totalHits": 0, "suggestions": []}}
        }
        result = await tools["wikijs_search_pages"](ctx=make_ctx(mock_client), query="zzz")
        assert "No pages found" in result

    async def test_client_error_returns_error_string(self, tools, mock_client):
        mock_client.query.side_effect = WikiJSError("internal error")
        result = await tools["wikijs_search_pages"](ctx=make_ctx(mock_client), query="test")
        assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# wikijs_list_pages
# ---------------------------------------------------------------------------

class TestListPagesTool:
    def _pages(self, n: int) -> list:
        return [
            {"id": i, "title": f"Page {i}", "path": f"page-{i}", "locale": "en",
             "description": "", "createdAt": "2024-01-01", "updatedAt": "2024-01-01"}
            for i in range(1, n + 1)
        ]

    async def test_paginated_json(self, tools, mock_client):
        mock_client.query.return_value = {"pages": {"list": self._pages(30)}}
        result = await tools["wikijs_list_pages"](
            ctx=make_ctx(mock_client), limit=10, offset=0
        )
        data = json.loads(result)
        assert data["total"] == 30
        assert data["count"] == 10
        assert data["has_more"] is True
        assert data["next_offset"] == 10

    async def test_second_page(self, tools, mock_client):
        mock_client.query.return_value = {"pages": {"list": self._pages(15)}}
        result = await tools["wikijs_list_pages"](
            ctx=make_ctx(mock_client), limit=10, offset=10
        )
        data = json.loads(result)
        assert data["count"] == 5
        assert data["has_more"] is False

    async def test_markdown_format(self, tools, mock_client):
        mock_client.query.return_value = {"pages": {"list": self._pages(3)}}
        result = await tools["wikijs_list_pages"](
            ctx=make_ctx(mock_client), response_format=ResponseFormat.MARKDOWN
        )
        assert "# Wiki.js Pages" in result

    async def test_client_error(self, tools, mock_client):
        mock_client.query.side_effect = WikiJSError("oops")
        result = await tools["wikijs_list_pages"](ctx=make_ctx(mock_client))
        assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# wikijs_get_page
# ---------------------------------------------------------------------------

class TestGetPageTool:
    def _full_page(self, **overrides):
        base = {
            "id": 15, "title": "Test Page", "path": "test",
            "description": "A test page", "content": "# Test\n\nBody.",
            "locale": "en", "editor": "markdown",
            "isPublished": True, "isPrivate": False,
            "tags": [{"tag": "docs"}, {"tag": "test"}],
            "createdAt": "2024-01-01", "updatedAt": "2024-06-01",
        }
        return {**base, **overrides}

    async def test_json_response_flattens_tags(self, tools, mock_client):
        mock_client.query.return_value = {"pages": {"single": self._full_page()}}
        result = await tools["wikijs_get_page"](ctx=make_ctx(mock_client), page_id=15)
        data = json.loads(result)
        assert data["id"] == 15
        assert data["tags"] == ["docs", "test"]

    async def test_markdown_response(self, tools, mock_client):
        mock_client.query.return_value = {"pages": {"single": self._full_page()}}
        result = await tools["wikijs_get_page"](
            ctx=make_ctx(mock_client), page_id=15,
            response_format=ResponseFormat.MARKDOWN,
        )
        assert "# Test Page" in result
        assert "Body." in result

    async def test_page_not_found_returns_error(self, tools, mock_client):
        mock_client.query.return_value = {"pages": {"single": None}}
        result = await tools["wikijs_get_page"](ctx=make_ctx(mock_client), page_id=999)
        assert "not found" in result.lower()
        assert "999" in result

    async def test_client_error(self, tools, mock_client):
        mock_client.query.side_effect = WikiJSError("server error")
        result = await tools["wikijs_get_page"](ctx=make_ctx(mock_client), page_id=1)
        assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# wikijs_get_page_by_path
# ---------------------------------------------------------------------------

class TestGetPageByPathTool:
    def _full_page(self):
        return {
            "id": 7, "title": "Home", "path": "home", "description": "",
            "content": "Welcome!", "locale": "en", "editor": "markdown",
            "isPublished": True, "isPrivate": False, "tags": [],
            "createdAt": "2024-01-01", "updatedAt": "2024-01-01",
        }

    async def test_json_response(self, tools, mock_client):
        mock_client.query.return_value = {"pages": {"singleByPath": self._full_page()}}
        result = await tools["wikijs_get_page_by_path"](
            ctx=make_ctx(mock_client), path="home"
        )
        data = json.loads(result)
        assert data["id"] == 7
        assert data["tags"] == []

    async def test_path_not_found(self, tools, mock_client):
        mock_client.query.return_value = {"pages": {"singleByPath": None}}
        result = await tools["wikijs_get_page_by_path"](
            ctx=make_ctx(mock_client), path="missing/path"
        )
        assert "No page found" in result
        assert "missing/path" in result


# ---------------------------------------------------------------------------
# wikijs_create_page
# ---------------------------------------------------------------------------

class TestCreatePageTool:
    def _mutate_result(self, page_id=42, path="guides/test", message=None):
        return {
            "pages": {
                "create": {
                    "responseResult": {
                        "succeeded": True, "message": message, "errorCode": None
                    },
                    "page": {"id": page_id, "path": path},
                }
            }
        }

    async def test_successful_create_returns_json(self, tools, mock_client):
        mock_client.mutate.return_value = self._mutate_result()
        result = await tools["wikijs_create_page"](
            ctx=make_ctx(mock_client),
            title="Test Guide", path="guides/test", content="# Test",
        )
        data = json.loads(result)
        assert data["succeeded"] is True
        assert data["page_id"] == 42
        assert data["path"] == "guides/test"

    async def test_default_message_when_none(self, tools, mock_client):
        mock_client.mutate.return_value = self._mutate_result(message=None)
        result = await tools["wikijs_create_page"](
            ctx=make_ctx(mock_client),
            title="T", path="p", content="c",
        )
        data = json.loads(result)
        assert data["message"]  # not empty

    async def test_leading_slash_stripped_before_api_call(self, tools, mock_client):
        mock_client.mutate.return_value = self._mutate_result(path="guides/test")
        await tools["wikijs_create_page"](
            ctx=make_ctx(mock_client),
            title="T", path="/guides/test", content="c",
        )
        variables = mock_client.mutate.call_args[0][1]
        assert not variables["path"].startswith("/")

    async def test_tags_default_to_empty_list(self, tools, mock_client):
        mock_client.mutate.return_value = self._mutate_result()
        await tools["wikijs_create_page"](
            ctx=make_ctx(mock_client),
            title="T", path="p", content="c",
        )
        variables = mock_client.mutate.call_args[0][1]
        assert variables["tags"] == []

    async def test_client_error(self, tools, mock_client):
        mock_client.mutate.side_effect = WikiJSError("path exists")
        result = await tools["wikijs_create_page"](
            ctx=make_ctx(mock_client),
            title="T", path="p", content="c",
        )
        assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# wikijs_update_page
# ---------------------------------------------------------------------------

class TestUpdatePageTool:
    def _current_page(self):
        return {
            "id": 15, "title": "Old Title", "content": "Old content",
            "description": "Old desc", "locale": "en", "editor": "markdown",
            "isPublished": True, "isPrivate": False,
            "tags": [{"tag": "old-tag"}],
            "createdAt": "2024-01-01", "updatedAt": "2024-01-01",
        }

    def _update_result(self):
        return {
            "pages": {
                "update": {
                    "responseResult": {"succeeded": True, "message": None, "errorCode": None},
                    "page": {"id": 15},
                }
            }
        }

    async def test_successful_update(self, tools, mock_client):
        mock_client.query.return_value = {"pages": {"single": self._current_page()}}
        mock_client.mutate.return_value = self._update_result()
        result = await tools["wikijs_update_page"](
            ctx=make_ctx(mock_client), page_id=15, title="New Title"
        )
        data = json.loads(result)
        assert data["succeeded"] is True
        assert data["page_id"] == 15

    async def test_title_override_sent_to_api(self, tools, mock_client):
        mock_client.query.return_value = {"pages": {"single": self._current_page()}}
        mock_client.mutate.return_value = self._update_result()
        await tools["wikijs_update_page"](
            ctx=make_ctx(mock_client), page_id=15, title="New Title"
        )
        variables = mock_client.mutate.call_args[0][1]
        assert variables["title"] == "New Title"

    async def test_unspecified_fields_preserved_from_current(self, tools, mock_client):
        mock_client.query.return_value = {"pages": {"single": self._current_page()}}
        mock_client.mutate.return_value = self._update_result()
        await tools["wikijs_update_page"](
            ctx=make_ctx(mock_client), page_id=15, title="New Title"
        )
        variables = mock_client.mutate.call_args[0][1]
        # content not supplied → should keep "Old content"
        assert variables["content"] == "Old content"
        assert variables["tags"] == ["old-tag"]

    async def test_page_not_found_during_fetch(self, tools, mock_client):
        mock_client.query.return_value = {"pages": {"single": None}}
        result = await tools["wikijs_update_page"](
            ctx=make_ctx(mock_client), page_id=999, title="X"
        )
        assert "not found" in result.lower()

    async def test_fetch_error_handled(self, tools, mock_client):
        mock_client.query.side_effect = WikiJSError("network error")
        result = await tools["wikijs_update_page"](
            ctx=make_ctx(mock_client), page_id=1, title="X"
        )
        assert result.startswith("Error:")

    async def test_mutate_error_handled(self, tools, mock_client):
        mock_client.query.return_value = {"pages": {"single": self._current_page()}}
        mock_client.mutate.side_effect = WikiJSError("update failed")
        result = await tools["wikijs_update_page"](
            ctx=make_ctx(mock_client), page_id=15, content="new content"
        )
        assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# wikijs_delete_page
# ---------------------------------------------------------------------------

class TestDeletePageTool:
    async def test_successful_delete(self, tools, mock_client):
        mock_client.mutate.return_value = {
            "pages": {
                "delete": {
                    "responseResult": {"succeeded": True, "message": None, "errorCode": None},
                }
            }
        }
        result = await tools["wikijs_delete_page"](ctx=make_ctx(mock_client), page_id=42)
        data = json.loads(result)
        assert data["succeeded"] is True
        assert data["page_id"] == 42

    async def test_default_message_when_none(self, tools, mock_client):
        mock_client.mutate.return_value = {
            "pages": {
                "delete": {
                    "responseResult": {"succeeded": True, "message": None, "errorCode": None},
                }
            }
        }
        result = await tools["wikijs_delete_page"](ctx=make_ctx(mock_client), page_id=1)
        data = json.loads(result)
        assert data["message"]  # not empty

    async def test_client_error(self, tools, mock_client):
        mock_client.mutate.side_effect = WikiJSError("Cannot delete system page")
        result = await tools["wikijs_delete_page"](ctx=make_ctx(mock_client), page_id=1)
        assert result.startswith("Error:")

    async def test_correct_id_sent_to_api(self, tools, mock_client):
        mock_client.mutate.return_value = {
            "pages": {
                "delete": {
                    "responseResult": {"succeeded": True, "message": None, "errorCode": None},
                }
            }
        }
        await tools["wikijs_delete_page"](ctx=make_ctx(mock_client), page_id=77)
        variables = mock_client.mutate.call_args[0][1]
        assert variables["id"] == 77
