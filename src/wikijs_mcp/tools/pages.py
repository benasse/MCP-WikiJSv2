"""Wiki.js page tools registered with FastMCP."""

import json
from typing import TYPE_CHECKING

from ..errors import _handle_api_error
from ..models import (
    ResponseFormat,
    SearchPagesInput,
    ListPagesInput,
    GetPageInput,
    GetPageByPathInput,
    CreatePageInput,
    UpdatePageInput,
    DeletePageInput,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP, Context


# ---------------------------------------------------------------------------
# GraphQL fragments
# ---------------------------------------------------------------------------

_PAGE_SUMMARY_FIELDS = "id path title description locale createdAt updatedAt"
_PAGE_FULL_FIELDS = "id path title description content locale editor isPublished isPrivate tags { tag } createdAt updatedAt"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _page_summary_to_md(page: dict) -> str:
    lines = [
        f"## {page.get('title', '(untitled)')} (id: {page.get('id')})",
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
        f"# {page.get('title', '(untitled)')} (id: {page.get('id')})",
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
    async def wikijs_search_pages(params: SearchPagesInput, ctx: "Context") -> str:
        """Search Wiki.js pages by full-text query.

        Searches the full text index of all Wiki.js pages and returns ranked
        results with page IDs, titles, paths, descriptions, and locales.

        Args:
            params (SearchPagesInput): Validated input containing:
                - query (str): Search terms (e.g. 'docker installation guide')
                - response_format (str): 'json' (default) or 'markdown'

        Returns:
            str: JSON or Markdown list of matching pages with fields:
                id, title, path, description, locale.
                Includes `totalHits` and `suggestions` from Wiki.js.

        Examples:
            - Find pages about Docker: query='docker'
            - Search for installation steps: query='install setup'
        """
        client = ctx.request_context.lifespan_state["client"]
        gql = """
        query SearchPages($query: String!) {
          pages {
            search(query: $query) {
              results {
                id
                title
                path
                description
                locale
              }
              suggestions
              totalHits
            }
          }
        }
        """
        try:
            data = await client.query(gql, {"query": params.query})
            search = data["pages"]["search"]
            results = search.get("results", [])
            total_hits = search.get("totalHits", 0)
            suggestions = search.get("suggestions", [])

            if not results:
                hint = f" Suggestions: {', '.join(suggestions)}" if suggestions else ""
                return f"No pages found matching '{params.query}'.{hint}"

            if params.response_format == ResponseFormat.MARKDOWN:
                lines = [
                    f"# Search Results: '{params.query}'",
                    f"Found {total_hits} matching page(s).",
                    "",
                ]
                for page in results:
                    lines.append(_page_summary_to_md(page))
                    lines.append("")
                if suggestions:
                    lines.append(f"**Suggestions**: {', '.join(suggestions)}")
                return "\n".join(lines)

            return json.dumps(
                {"totalHits": total_hits, "suggestions": suggestions, "results": results},
                indent=2,
            )
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
    async def wikijs_list_pages(params: ListPagesInput, ctx: "Context") -> str:
        """List all Wiki.js pages with optional sorting and pagination.

        Returns a paginated list of pages ordered by the chosen field. Use
        `offset` and `limit` to page through large wikis.

        Args:
            params (ListPagesInput): Validated input containing:
                - limit (int): Pages per page, 1–100 (default 20)
                - offset (int): Starting index (default 0)
                - order_by (str): 'TITLE', 'PATH', 'CREATED', or 'UPDATED'
                - response_format (str): 'json' or 'markdown'

        Returns:
            str: Paginated result with keys: total, count, offset, items,
                 has_more, next_offset. Each item: id, path, title, locale,
                 createdAt, updatedAt.

        Examples:
            - List first 20 pages: use defaults
            - Next page: offset=20, limit=20
            - Sorted by update time: order_by='UPDATED'
        """
        client = ctx.request_context.lifespan_state["client"]
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
            data = await client.query(gql, {"orderBy": params.order_by})
            all_pages = data["pages"]["list"]
            page_slice = _paginate(all_pages, params.limit, params.offset)

            if params.response_format == ResponseFormat.MARKDOWN:
                items = page_slice["items"]
                lines = [
                    f"# Wiki.js Pages (sorted by {params.order_by})",
                    f"Showing {page_slice['count']} of {page_slice['total']} pages (offset {page_slice['offset']}).",
                    "",
                ]
                for page in items:
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
    async def wikijs_get_page(params: GetPageInput, ctx: "Context") -> str:
        """Fetch the full content and metadata of a Wiki.js page by its numeric ID.

        Use this when you already know the page ID (e.g. from search results or
        the list tool). Returns the complete page including content body.

        Args:
            params (GetPageInput): Validated input containing:
                - page_id (int): Numeric page ID (e.g. 15)
                - response_format (str): 'json' or 'markdown'

        Returns:
            str: Full page data including: id, path, title, description,
                 content, locale, editor, isPublished, isPrivate, tags,
                 createdAt, updatedAt.

            Error response: "Error: <message>" string.

        Examples:
            - Get page with ID 15: page_id=15
        """
        client = ctx.request_context.lifespan_state["client"]
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
            data = await client.query(gql, {"id": params.page_id})
            page = data["pages"]["single"]
            if page is None:
                return f"Error: Page with ID {params.page_id} not found."

            if params.response_format == ResponseFormat.MARKDOWN:
                return _page_full_to_md(page)

            # Flatten tags for JSON
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
    async def wikijs_get_page_by_path(params: GetPageByPathInput, ctx: "Context") -> str:
        """Fetch the full content and metadata of a Wiki.js page by its URL path.

        Use this when you know the page's path but not its ID. Requires
        administrator privileges on the Wiki.js API key.

        Args:
            params (GetPageByPathInput): Validated input containing:
                - path (str): Page URL path, e.g. 'home' or 'guides/installation'
                - locale (str): Locale code, e.g. 'en' (default 'en')
                - response_format (str): 'json' or 'markdown'

        Returns:
            str: Full page data (same schema as wikijs_get_page).

        Examples:
            - Get home page: path='home', locale='en'
            - Get nested page: path='docs/api/overview'
        """
        client = ctx.request_context.lifespan_state["client"]
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
            data = await client.query(gql, {"path": params.path, "locale": params.locale})
            page = data["pages"]["singleByPath"]
            if page is None:
                return f"Error: No page found at path '{params.path}' (locale: {params.locale})."

            if params.response_format == ResponseFormat.MARKDOWN:
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
    async def wikijs_create_page(params: CreatePageInput, ctx: "Context") -> str:
        """Create a new page in Wiki.js.

        Creates a page at the given path with Markdown content. The path must
        not already exist. Returns the new page's ID and path on success.

        Args:
            params (CreatePageInput): Validated input containing:
                - title (str): Page title (e.g. 'Installation Guide')
                - path (str): URL path, no leading slash (e.g. 'guides/install')
                - content (str): Page body in Markdown format
                - description (str): Optional short description/summary
                - locale (str): Locale code, default 'en'
                - editor (str): 'markdown' (default), 'ckeditor', 'code', 'asciidoc'
                - is_published (bool): Publish immediately, default True
                - is_private (bool): Private page, default False
                - tags (List[str]): Tags to attach, default []

        Returns:
            str: JSON with keys: succeeded, page_id, path, message.
                 Error string on failure.

        Examples:
            - Create a Markdown guide: title='Setup Guide', path='setup',
              content='# Setup\n\nFollow these steps...'
        """
        client = ctx.request_context.lifespan_state["client"]
        gql = """
        mutation CreatePage(
          $title: String!
          $path: String!
          $content: String!
          $description: String!
          $locale: String!
          $editor: String!
          $isPublished: Boolean!
          $isPrivate: Boolean!
          $tags: [String]!
        ) {
          pages {
            create(
              title: $title
              path: $path
              content: $content
              description: $description
              locale: $locale
              editor: $editor
              isPublished: $isPublished
              isPrivate: $isPrivate
              tags: $tags
            ) {
              responseResult {
                succeeded
                errorCode
                message
              }
              page {
                id
                path
              }
            }
          }
        }
        """
        variables = {
            "title": params.title,
            "path": params.path,
            "content": params.content,
            "description": params.description or "",
            "locale": params.locale,
            "editor": params.editor,
            "isPublished": params.is_published,
            "isPrivate": params.is_private,
            "tags": params.tags or [],
        }
        try:
            data = await client.mutate(gql, variables)
            payload = data["pages"]["create"]
            page = payload.get("page") or {}
            return json.dumps(
                {
                    "succeeded": True,
                    "page_id": page.get("id"),
                    "path": page.get("path"),
                    "message": payload["responseResult"].get("message") or "Page created successfully.",
                },
                indent=2,
            )
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
    async def wikijs_update_page(params: UpdatePageInput, ctx: "Context") -> str:
        """Update an existing Wiki.js page by ID.

        Fetches the current page first to preserve unspecified fields, then
        applies only the provided changes. At least one optional field must be
        provided.

        Args:
            params (UpdatePageInput): Validated input containing:
                - page_id (int): ID of the page to update (required)
                - title (str): New title, or None to keep current
                - content (str): New content body, or None to keep current
                - description (str): New description, or None to keep current
                - tags (List[str]): Replacement tag list, or None to keep current
                - is_published (bool): Change publish status, or None to keep
                - is_private (bool): Change private status, or None to keep

        Returns:
            str: JSON with keys: succeeded, page_id, message.
                 Error string on failure.

        Examples:
            - Fix a typo: page_id=15, content='# Fixed\n\nCorrected text.'
            - Unpublish a draft: page_id=15, is_published=False
            - Update tags: page_id=15, tags=['devops', 'linux']
        """
        client = ctx.request_context.lifespan_state["client"]

        # Fetch current state to fill in unspecified fields
        fetch_gql = f"""
        query GetPage($id: Int!) {{
          pages {{
            single(id: $id) {{
              {_PAGE_FULL_FIELDS}
            }}
          }}
        }}
        """
        try:
            fetch_data = await client.query(fetch_gql, {"id": params.page_id})
            current = fetch_data["pages"]["single"]
            if current is None:
                return f"Error: Page with ID {params.page_id} not found."
        except Exception as e:
            return _handle_api_error(e)

        current_tags = [t["tag"] for t in (current.get("tags") or [])]

        gql = """
        mutation UpdatePage(
          $id: Int!
          $title: String!
          $content: String!
          $description: String!
          $editor: String!
          $isPublished: Boolean!
          $isPrivate: Boolean!
          $tags: [String]!
        ) {
          pages {
            update(
              id: $id
              title: $title
              content: $content
              description: $description
              editor: $editor
              isPublished: $isPublished
              isPrivate: $isPrivate
              tags: $tags
            ) {
              responseResult {
                succeeded
                errorCode
                message
              }
              page {
                id
              }
            }
          }
        }
        """
        variables = {
            "id": params.page_id,
            "title": params.title if params.title is not None else current["title"],
            "content": params.content if params.content is not None else current["content"],
            "description": params.description if params.description is not None else (current.get("description") or ""),
            "editor": current.get("editor", "markdown"),
            "isPublished": params.is_published if params.is_published is not None else current.get("isPublished", True),
            "isPrivate": params.is_private if params.is_private is not None else current.get("isPrivate", False),
            "tags": params.tags if params.tags is not None else current_tags,
        }
        try:
            data = await client.mutate(gql, variables)
            payload = data["pages"]["update"]
            return json.dumps(
                {
                    "succeeded": True,
                    "page_id": params.page_id,
                    "message": payload["responseResult"].get("message") or "Page updated successfully.",
                },
                indent=2,
            )
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
    async def wikijs_delete_page(params: DeletePageInput, ctx: "Context") -> str:
        """Permanently delete a Wiki.js page by ID. This action cannot be undone.

        Use wikijs_get_page or wikijs_search_pages first to confirm the correct
        page ID before deleting.

        Args:
            params (DeletePageInput): Validated input containing:
                - page_id (int): Numeric ID of the page to delete

        Returns:
            str: JSON with keys: succeeded, page_id, message.
                 Error string on failure.

        Examples:
            - Delete page 42: page_id=42
        """
        client = ctx.request_context.lifespan_state["client"]
        gql = """
        mutation DeletePage($id: Int!) {
          pages {
            delete(id: $id) {
              responseResult {
                succeeded
                errorCode
                message
              }
            }
          }
        }
        """
        try:
            data = await client.mutate(gql, {"id": params.page_id})
            payload = data["pages"]["delete"]
            return json.dumps(
                {
                    "succeeded": True,
                    "page_id": params.page_id,
                    "message": payload["responseResult"].get("message") or "Page deleted successfully.",
                },
                indent=2,
            )
        except Exception as e:
            return _handle_api_error(e)
