# MCP Server for Wiki.js v2

A Python MCP (Model Context Protocol) server that enables LLMs and AI agents to search, read, create, edit, and delete pages on a [Wiki.js v2](https://js.wiki) instance via its GraphQL API.

## Features

- **Search pages** — full-text search across all wiki content
- **List pages** — paginated page listing with sorting options
- **Get page** — fetch full page content by ID or by path
- **Create page** — create new Markdown pages
- **Update page** — partial updates (only changed fields required)
- **Delete page** — permanently remove pages

## Prerequisites

- Docker and Docker Compose
- A running Wiki.js v2 instance (v2.2+)
- A Wiki.js API key (Administration → API Access)

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url>
cd MCP-WikiJSv2

# 2. Configure environment
cp .env.example .env
$EDITOR .env   # fill in MCP_API_KEY, WIKIJS_URL, WIKIJS_API_KEY

# 3. Start the server
docker compose up --build
```

The server will be available at `http://localhost:8000`.

## Configuration

All configuration is via environment variables (`.env` file):

| Variable | Required | Default | Description |
|---|---|---|---|
| `MCP_API_KEY` | Yes | — | Bearer token that MCP clients use to authenticate to this server |
| `WIKIJS_URL` | Yes | — | Base URL of your Wiki.js instance, e.g. `http://wikijs:3000` |
| `WIKIJS_API_KEY` | Yes | — | API key from Wiki.js admin panel |
| `MCP_HOST` | No | `0.0.0.0` | Bind address |
| `MCP_PORT` | No | `8000` | Port |
| `LOG_LEVEL` | No | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

Generate a strong `MCP_API_KEY`:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Connecting an MCP Client

Configure your MCP client (e.g. Claude Desktop, Cursor) to connect via **streamable HTTP**:

```json
{
  "mcpServers": {
    "wikijs": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer <your-MCP_API_KEY>"
      }
    }
  }
}
```

### Inspect with MCP Inspector

```bash
npx @modelcontextprotocol/inspector http://localhost:8000/mcp \
  --header "Authorization: Bearer <your-MCP_API_KEY>"
```

## Available Tools

| Tool | Description |
|---|---|
| `wikijs_search_pages` | Full-text search across all pages |
| `wikijs_list_pages` | List pages with pagination and sort order |
| `wikijs_get_page` | Fetch complete page content by numeric ID |
| `wikijs_get_page_by_path` | Fetch page by URL path and locale |
| `wikijs_create_page` | Create a new page |
| `wikijs_update_page` | Update title, content, tags, or status |
| `wikijs_delete_page` | Permanently delete a page |

All tools support `response_format: "json"` (default) or `"markdown"`.

## Security

- Clients authenticate to this server with a bearer token (`MCP_API_KEY`)
- Token comparison uses `hmac.compare_digest` to prevent timing attacks
- This server authenticates to Wiki.js with a separate API key (`WIKIJS_API_KEY`)
- The Docker container runs as a non-root user, with all Linux capabilities dropped and a read-only root filesystem

## Development

```bash
# Install dependencies (requires Python 3.11+)
pip install -e ".[dev]"

# Run locally (requires .env)
python -m wikijs_mcp.server

# Syntax check
python -m py_compile src/wikijs_mcp/server.py
```

## Project Structure

```
src/wikijs_mcp/
├── server.py        # FastMCP entry point, auth middleware, uvicorn launch
├── client.py        # Async GraphQL client for Wiki.js
├── models.py        # Pydantic input models
├── errors.py        # Error types and handler
└── tools/
    └── pages.py     # All 7 page tools
```
