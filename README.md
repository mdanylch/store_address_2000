# Store Address MCP (single file)

One Python module (`server.py`) runs a [FastMCP](https://github.com/jlowin/fastmcp) server over **HTTP**, so you can deploy it behind **Uvicorn** (including **AWS App Runner**).

## What it does

| Tool | Behavior |
|------|----------|
| `get_store_locations` | If the user’s text mentions Amsterdam, Paris, or Lisbon (key or city name), returns that store’s address. Otherwise returns all stores. |
| `get_bulk_pricing` | If the text contains a number, POSTs the prompt to an external API and returns the JSON response (or an error). |

Store data is a small in-memory dict in `server.py` (no database).

## How it works (architecture)

1. **`FastMCP`** registers async functions decorated with `@mcp.tool()` as MCP tools. Descriptions on those functions help the host model choose when to call them.
2. **`mcp.http_app(path="/mcp")`** builds an **ASGI** application (Starlette-based) that speaks MCP over HTTP on the **`/mcp`** path.
3. **`uvicorn server:app`** loads the module `server` and the variable **`app`**, which is that ASGI callable. App Runner (or any container) runs the same command.

```text
Client (MCP over HTTP) → Uvicorn → app → /mcp → FastMCP → tools
```

## Run locally

```bash
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8000
```

MCP HTTP endpoint base path: **`http://<host>:8000/mcp`**. Point your MCP client at that URL per its docs (transport type must match what FastMCP exposes for your version).

## Deploy on AWS App Runner (outline)

- Use a **Dockerfile** or App Runner’s **Python** build: install `requirements.txt`, start command `uvicorn server:app --host 0.0.0.0 --port 8080` (or the port App Runner sets via `PORT`).
- Configure **HTTPS** in front of the service; do not expose plain HTTP to the public internet without TLS termination at the load balancer.

## Files

| File | Role |
|------|------|
| `server.py` | MCP tools + `app` ASGI entrypoint + inline documentation |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Ignores venvs and caches |
