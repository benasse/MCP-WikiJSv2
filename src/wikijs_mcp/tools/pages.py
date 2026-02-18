"""Wiki.js page tools registered with FastMCP."""

import json
from typing import TYPE_CHECKING, Annotated, Optional, List

from mcp.server.fastmcp import Context
from pydantic import Field

from ..errors import _handle_api_error
from ..models import ResponseFormat

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


# ---------------------------------------------------------------------------
# GraphQL field sets
# ---------------------------------------------------------------------------

_PAGE_SUMMARY_FIELDS = "id path title description locale createdAt updatedAt"
_PAGE_FULL_FIELDS = "id path title description content locale editor isPublished isPrivate tags { tag } createdAt updatedAt"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _page_summary_to_md(page: dict) -> str:
    lines = [
        f"## {page.get('title') or '(untitled)'} (id: {page.get('id')})",
        f"- **Path**: `{page.get('path')}`",
        f"- **Locale**: {page.get('locale')}",
    ]
    if desc := page.get("description"):
        lines.append(f"- **Description**: {desc}")
    lines.append(f"- **Created**: {page.get('createdAt')}  **Updated**: {page.get('updatedAt')}")
    return "\n".join(lines)


def _page_full_to_md(page: dict) -> str:
    tags = [t["tag"] for t in (page.get("tags") or [])]
    lines = [
        f"# {page.get('title') or '(untitled)'} (id: {page.get('id')})",
        f"- **Path**: `{page.get('path')}`",
        f"- **Locale**: {page.get('locale')}",
        f"- **Editor**: {page.get('editor')}",
        f"- **Published**: {page.get('isPublished')}  **Private**: {page.get('isPrivate')}",
        f"- **Tags**: {', '.join(tags) or 'none'}",
        f"- **Created**: {page.get('createdAt')}  **Updated**: {page.get('updatedAt')}",
        "",
        "---",
        "",
        page.get("content") or "",
    ]
    return "\n".join(lines)


def _paginate(items: list, limit: int, offset: int) -> dict:
    total = len(items)
    page_items = items[offset: offset + limit]
    return {
        "total": total,
        "count": len(page_items),
        "offset": offset,
        "items": page_items,
        "has_more": total > offset + len(page_items),
        "next_offset": (offset + len(page_items)) if total > offset + len(page_items) else None,
    }


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["client"]


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_page_tools(mcp: "FastMCP") -> None:
    """Register all page-related tools on the FastMCP instance."""

    @mcp.tool(
        name="wikijs_search_pages",
        annotations={
            "title": "Search Wiki.js Pages",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def wikijs_search_pages(
        ctx: Context,
        query: Annotated[str, Field(description="Full-text search query (e.g. 'installation guide')", min_length=1, max_length=500)],
        response_format: Annotated[ResponseFormat, Field(description="Output format: 'json' or 'markdown'")] = ResponseFormat.JSON,
    ) -> str:
        """Search Wiki.js pages by full-text query.

        Searches the full text index of all Wiki.js pages and returns ranked results.

        Returns:
            JSON: {totalHits, suggestions, results: [{id, title, path, description, locale}]}
            Markdown: formatted list of matching pages.

        Examples:
            - Find Docker pages: query='docker'
            - Find installation guides: query='install setup'
        """
        client = _client(ctx)
        gql = """
        query SearchPages($query: String!) {
          pages {
            search(query: $query) {
              results { id title path description locale }
              suggestions
              totalHits
            }
          }
        }
        """
        try:
            data = await client.query(gql, {"query": query})
            search = data["pages"]["search"]
            results = search.get("results", [])
            total_hits = search.get("totalHits", 0)
            suggestions = search.get("suggestions", [])

            if not results:
                hint = f" Suggestions: {', '.join(suggestions)}" if suggestions else ""
                return f"No pages found matching '{query}'.{hint}"

            if response_format == ResponseFormat.MARKDOWN:
                lines = [f"# Search Results: '{query}'", f"Found {total_hits} matching page(s).", ""]
                for page in results:
                    lines.append(_page_summary_to_md(page))
                    lines.append("")
                if suggestions:
                    lines.append(f"**Suggestions**: {', '.join(suggestions)}")
                return "\n".join(lines)

            return json.dumps({"totalHits": total_hits, "suggestions": suggestions, "results": results}, indent=2)
        except Exception as e:
            return _handle_api_error(e)

    @mcp.tool(
        name="wikijs_list_pages",
        annotations={
            "title": "List Wiki.js Pages",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def wikijs_list_pages(
        ctx: Context,
        limit: Annotated[int, Field(description="Maximum pages to return (1–100)", ge=1, le=100)] = 20,
        offset: Annotated[int, Field(description="Number of pages to skip for pagination", ge=0)] = 0,
        order_by: Annotated[str, Field(description="Sort order: 'TITLE', 'PATH', 'CREATED', or 'UPDATED'")] = "TITLE",
        response_format: Annotated[ResponseFormat, Field(description="Output format: 'json' or 'markdown'")] = ResponseFormat.JSON,
    ) -> str:
        """List all Wiki.js pages with optional sorting and pagination.

        Returns a paginated list ordered by the chosen field.

        Returns:
            JSON: {total, count, offset, items: [{id, path, title, locale, createdAt, updatedAt}], has_more, next_offset}

        Examples:
            - List first 20 pages: use defaults
            - Next page: offset=20
            - Sort by update time: order_by='UPDATED'
        """
        client = _client(ctx)
        order_by = order_by.upper()
        gql = f"""
        query ListPages($orderBy: PageOrderBy) {{
          pages {{
            list(orderBy: $orderBy) {{
              {_PAGE_SUMMARY_FIELDS}
            }}
          }}
        }}
        """
        try:
            data = await client.query(gql, {"orderBy": order_by})
            all_pages = data["pages"]["list"]
            page_slice = _paginate(all_pages, limit, offset)

            if response_format == ResponseFormat.MARKDOWN:
                lines = [
                    f"# Wiki.js Pages (sorted by {order_by})",
                    f"Showing {page_slice['count']} of {page_slice['total']} pages (offset {page_slice['offset']}).",
                    "",
                ]
                for page in page_slice["items"]:
                    lines.append(_page_summary_to_md(page))
                    lines.append("")
                if page_slice["has_more"]:
                    lines.append(f"*More pages available — use offset={page_slice['next_offset']}*")
                return "\n".join(lines)

            return json.dumps(page_slice, indent=2)
        except Exception as e:
            return _handle_api_error(e)

    @mcp.tool(
        name="wikijs_get_page",
        annotations={
            "title": "Get Wiki.js Page by ID",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def wikijs_get_page(
        ctx: Context,
        page_id: Annotated[int, Field(description="Numeric page ID (e.g. 15)", ge=1)],
        response_format: Annotated[ResponseFormat, Field(description="Output format: 'json' or 'markdown'")] = ResponseFormat.JSON,
    ) -> str:
        """Fetch full content and metadata of a Wiki.js page by its numeric ID.

        Returns:
            JSON: {id, path, title, description, content, locale, editor,
                   isPublished, isPrivate, tags, createdAt, updatedAt}

        Examples:
            - Get page 15: page_id=15
        """
        client = _client(ctx)
        gql = f"""
        query GetPage($id: Int!) {{
          pages {{
            single(id: $id) {{
              {_PAGE_FULL_FIELDS}
            }}
          }}
        }}
        """
        try:
            data = await client.query(gql, {"id": page_id})
            page = data["pages"]["single"]
            if page is None:
                return f"Error: Page with ID {page_id} not found."
            if response_format == ResponseFormat.MARKDOWN:
                return _page_full_to_md(page)
            page["tags"] = [t["tag"] for t in (page.get("tags") or [])]
            return json.dumps(page, indent=2)
        except Exception as e:
            return _handle_api_error(e)

    @mcp.tool(
        name="wikijs_get_page_by_path",
        annotations={
            "title": "Get Wiki.js Page by Path",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def wikijs_get_page_by_path(
        ctx: Context,
        path: Annotated[str, Field(description="Page URL path, e.g. 'home' or 'guides/installation'", min_length=1)],
        locale: Annotated[str, Field(description="Locale code, e.g. 'en' (default 'en')", min_length=2, max_length=10)] = "en",
        response_format: Annotated[ResponseFormat, Field(description="Output format: 'json' or 'markdown'")] = ResponseFormat.JSON,
    ) -> str:
        """Fetch full content and metadata of a Wiki.js page by its URL path.

        Requires administrator privileges on the Wiki.js API key.

        Returns:
            JSON: same schema as wikijs_get_page.

        Examples:
            - Get home page: path='home'
            - Get nested page: path='docs/api/overview', locale='en'
        """
        client = _client(ctx)
        gql = f"""
        query GetPageByPath($path: String!, $locale: String!) {{
          pages {{
            singleByPath(path: $path, locale: $locale) {{
              {_PAGE_FULL_FIELDS}
            }}
          }}
        }}
        """
        try:
            data = await client.query(gql, {"path": path, "locale": locale})
            page = data["pages"]["singleByPath"]
            if page is None:
                return f"Error: No page found at path '{path}' (locale: {locale})."
            if response_format == ResponseFormat.MARKDOWN:
                return _page_full_to_md(page)
            page["tags"] = [t["tag"] for t in (page.get("tags") or [])]
            return json.dumps(page, indent=2)
        except Exception as e:
            return _handle_api_error(e)

    @mcp.tool(
        name="wikijs_create_page",
        annotations={
            "title": "Create Wiki.js Page",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def wikijs_create_page(
        ctx: Context,
        title: Annotated[str, Field(description="Page title (e.g. 'Installation Guide')", min_length=1, max_length=255)],
        path: Annotated[str, Field(description="URL path, no leading slash (e.g. 'guides/install')", min_length=1)],
        content: Annotated[str, Field(description="Page body in Markdown format", min_length=1)],
        description: Annotated[str, Field(description="Short page description/summary")] = "",
        locale: Annotated[str, Field(description="Locale code, e.g. 'en'", min_length=2, max_length=10)] = "en",
        editor: Annotated[str, Field(description="Editor type: 'markdown' (default), 'ckeditor', 'code', 'asciidoc'")] = "markdown",
        is_published: Annotated[bool, Field(description="Publish immediately (default True)")] = True,
        is_private: Annotated[bool, Field(description="Make page private (default False)")] = False,
        tags: Annotated[Optional[List[str]], Field(description="Tags to attach to the page")] = None,
    ) -> str:
        """Create a new page in Wiki.js.

        The path must not already exist. Returns the new page's ID and path on success.

        Returns:
            JSON: {succeeded, page_id, path, message}

        Examples:
            - Create a guide: title='Setup Guide', path='setup',
              content='# Setup\\n\\nFollow these steps...'
        """
        client = _client(ctx)
        gql = """
        mutation CreatePage(
          $title: String! $path: String! $content: String! $description: String!
          $locale: String! $editor: String! $isPublished: Boolean! $isPrivate: Boolean!
          $tags: [String]!
        ) {
          pages {
            create(title: $title path: $path content: $content description: $description
                   locale: $locale editor: $editor isPublished: $isPublished
                   isPrivate: $isPrivate tags: $tags) {
              responseResult { succeeded errorCode message }
              page { id path }
            }
          }
        }
        """
        try:
            data = await client.mutate(gql, {
                "title": title, "path": path.lstrip("/"), "content": content,
                "description": description, "locale": locale, "editor": editor,
                "isPublished": is_published, "isPrivate": is_private,
                "tags": tags or [],
            })
            payload = data["pages"]["create"]
            page = payload.get("page") or {}
            return json.dumps({
                "succeeded": True,
                "page_id": page.get("id"),
                "path": page.get("path"),
                "message": payload["responseResult"].get("message") or "Page created successfully.",
            }, indent=2)
        except Exception as e:
            return _handle_api_error(e)

    @mcp.tool(
        name="wikijs_update_page",
        annotations={
            "title": "Update Wiki.js Page",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def wikijs_update_page(
        ctx: Context,
        page_id: Annotated[int, Field(description="Numeric ID of the page to update", ge=1)],
        title: Annotated[Optional[str], Field(description="New title, or omit to keep current")] = None,
        content: Annotated[Optional[str], Field(description="New Markdown content, or omit to keep current")] = None,
        description: Annotated[Optional[str], Field(description="New description, or omit to keep current")] = None,
        tags: Annotated[Optional[List[str]], Field(description="Replacement tag list (replaces all existing tags), or omit to keep current")] = None,
        is_published: Annotated[Optional[bool], Field(description="Change published status, or omit to keep current")] = None,
        is_private: Annotated[Optional[bool], Field(description="Change private status, or omit to keep current")] = None,
    ) -> str:
        """Update an existing Wiki.js page by ID.

        Fetches the current page first to preserve all unspecified fields.
        At least one optional field should be provided.

        Returns:
            JSON: {succeeded, page_id, message}

        Examples:
            - Fix content: page_id=15, content='# Fixed\\n\\nCorrected text.'
            - Unpublish: page_id=15, is_published=False
            - Update tags: page_id=15, tags=['devops', 'linux']
        """
        client = _client(ctx)

        # Fetch current state to preserve unspecified fields
        fetch_gql = f"""
        query GetPage($id: Int!) {{
          pages {{ single(id: $id) {{ {_PAGE_FULL_FIELDS} }} }}
        }}
        """
        try:
            fetch_data = await client.query(fetch_gql, {"id": page_id})
            current = fetch_data["pages"]["single"]
            if current is None:
                return f"Error: Page with ID {page_id} not found."
        except Exception as e:
            return _handle_api_error(e)

        current_tags = [t["tag"] for t in (current.get("tags") or [])]
        gql = """
        mutation UpdatePage(
          $id: Int! $title: String! $content: String! $description: String!
          $editor: String! $isPublished: Boolean! $isPrivate: Boolean! $tags: [String]!
        ) {
          pages {
            update(id: $id title: $title content: $content description: $description
                   editor: $editor isPublished: $isPublished isPrivate: $isPrivate tags: $tags) {
              responseResult { succeeded errorCode message }
              page { id }
            }
          }
        }
        """
        try:
            data = await client.mutate(gql, {
                "id": page_id,
                "title": title if title is not None else current["title"],
                "content": content if content is not None else current["content"],
                "description": description if description is not None else (current.get("description") or ""),
                "editor": current.get("editor", "markdown"),
                "isPublished": is_published if is_published is not None else current.get("isPublished", True),
                "isPrivate": is_private if is_private is not None else current.get("isPrivate", False),
                "tags": tags if tags is not None else current_tags,
            })
            payload = data["pages"]["update"]
            return json.dumps({
                "succeeded": True,
                "page_id": page_id,
                "message": payload["responseResult"].get("message") or "Page updated successfully.",
            }, indent=2)
        except Exception as e:
            return _handle_api_error(e)

    @mcp.tool(
        name="wikijs_delete_page",
        annotations={
            "title": "Delete Wiki.js Page",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def wikijs_delete_page(
        ctx: Context,
        page_id: Annotated[int, Field(description="Numeric ID of the page to delete", ge=1)],
    ) -> str:
        """Permanently delete a Wiki.js page by ID. This action cannot be undone.

        Use wikijs_search_pages or wikijs_get_page first to confirm the correct
        page ID before calling this tool.

        Returns:
            JSON: {succeeded, page_id, message}

        Examples:
            - Delete page 42: page_id=42
        """
        client = _client(ctx)
        gql = """
        mutation DeletePage($id: Int!) {
          pages {
            delete(id: $id) {
              responseResult { succeeded errorCode message }
            }
          }
        }
        """
        try:
            data = await client.mutate(gql, {"id": page_id})
            payload = data["pages"]["delete"]
            return json.dumps({
                "succeeded": True,
                "page_id": page_id,
                "message": payload["responseResult"].get("message") or "Page deleted successfully.",
            }, indent=2)
        except Exception as e:
            return _handle_api_error(e)
