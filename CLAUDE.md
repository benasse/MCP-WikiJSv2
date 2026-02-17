# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Python MCP server (`wikijs_mcp`) integrating with the Wiki.js v2 GraphQL API, enabling LLMs to read, search, create, and manage wiki pages and assets.

## Stack

- **Language**: Python 3.11+
- **Framework**: `mcp` (FastMCP) — `from mcp.server.fastmcp import FastMCP`
- **HTTP client**: `httpx` (async)
- **Validation**: Pydantic v2
- **Transport**: stdio (local) or streamable HTTP (remote)
- **Package manager**: `uv` (preferred) or `pip`

## Commands

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Run the server (stdio)
python server.py

# Verify syntax / imports
python -m py_compile server.py

# Test with MCP Inspector
npx @modelcontextprotocol/inspector python server.py
```

## Architecture

```
wikijs_mcp/
  server.py          # FastMCP entry point: mcp = FastMCP("wikijs_mcp")
  client.py          # Shared async httpx API client (GraphQL + REST)
  tools/             # One file per domain (pages.py, search.py, assets.py, …)
  models.py          # Shared Pydantic input/output models
  errors.py          # _handle_api_error() centralising httpx error mapping
```

All tools are registered with `@mcp.tool(name="wikijs_<action>_<resource>", annotations={...})`. Shared API calls live in `client.py`; no copy-pasted request logic in tool files.

## Tool Design Rules

**Naming**: `wikijs_{action}_{resource}` — e.g. `wikijs_search_pages`, `wikijs_create_page`, `wikijs_get_asset`.

**Input models**: Every tool uses a Pydantic `BaseModel` with `ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')`. All `Field()` entries include `description` and constraints.

**Annotations** (set on every tool):
```python
annotations={
    "readOnlyHint": True/False,
    "destructiveHint": True/False,
    "idempotentHint": True/False,
    "openWorldHint": True  # Wiki.js is an external service
}
```

**Responses**: Return JSON by default; support `response_format: ResponseFormat` (`"json"` | `"markdown"`) on list/get tools. Paginated list tools always return `{"total", "count", "offset", "items", "has_more", "next_offset"}`.

**Errors**: `_handle_api_error(e)` maps `httpx.HTTPStatusError` codes to actionable strings. Never propagate raw exceptions to callers.

**Async**: All tools and the shared client use `async def`. Use `async with httpx.AsyncClient()` per request or a lifespan-managed client.

## Pydantic v2 Reminders

- `model_config = ConfigDict(...)` (not nested `Config` class)
- `@field_validator` + `@classmethod` (not `@validator`)
- `model.model_dump()` (not `.dict()`)

## Karpathy Guidelines

1. **Think before coding** — state assumptions explicitly; surface ambiguities before implementing.
2. **Simplicity first** — minimum code that solves the problem; no speculative abstractions.
3. **Surgical changes** — touch only what the request requires; match existing style.
4. **Goal-driven execution** — define a verifiable success criterion for each task before starting.

## Quality Checklist (before finishing any tool)

- [ ] Tool name follows `wikijs_{action}_{resource}` pattern
- [ ] Pydantic input model with `Field()` descriptions and constraints
- [ ] Annotations set correctly (especially `readOnlyHint`)
- [ ] Comprehensive docstring with Args / Returns schema / Examples
- [ ] Error handling via `_handle_api_error`
- [ ] Pagination metadata returned for list tools
- [ ] No duplicated API-call logic — reuse `client.py` helpers
- [ ] `python -m py_compile` passes
