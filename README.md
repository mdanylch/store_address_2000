# Store Address MCP (single file)

One Python module (`server.py`) runs a [FastMCP](https://github.com/jlowin/fastmcp) server over **HTTP**, so you can deploy it behind **Uvicorn** (including **AWS App Runner**).

## What it does

| Tool | Behavior |
|------|----------|
| `get_store_locations` | If the user’s text mentions Amsterdam, Paris, or Lisbon (key or city name), returns that store’s address. Otherwise returns all stores. |

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

## AWS App Runner (Python 3.11)

Use the **GitHub** source for this repo. Suggested settings:

| Setting | Value |
|--------|--------|
| Runtime | Python 3.11 |
| Port | `8080` |
| **Build command** | **`sh start.sh`** |
| **Start command** | **`sh run.sh`** |

**Do not use the same script for both.** **`start.sh`** only installs packages into `deps/` and then **exits**. **`run.sh`** starts Uvicorn and must be the **Start** command. If **Start** is `sh start.sh`, `pip3 install …`, or anything that exits after install, you get **container exit code 0** and **nothing listening on 8080** (your app logs will show pip, then silence).

`start.sh` runs `pip3 install -r requirements.txt -t deps`, putting all wheels under **`deps/`** inside `/app`. That folder is included when App Runner copies `/app` into the **runtime** image (unlike packages installed only into the build image’s global `site-packages`).

`run.sh` sets **`PYTHONPATH`** to `./deps` and runs **`python3 -m uvicorn`** immediately—no pip on start, so the port is open right away for health checks.

**Health checks:** The app responds with **200** on **`/`** and **`/health`** so the default App Runner HTTP health check can succeed. MCP clients still use **`/mcp`**.

**Important:** The **start** command must be a long‑running process — use **`sh run.sh`** (install + Uvicorn), not `pip3 install` alone.

After deploy, the MCP URL is:

`https://<your-app-runner-domain>/mcp`

Configure **HTTPS** in front of the service; TLS is terminated at App Runner when you use the default service URL.

### Webex: CustomHeaderAuth

In App Runner, add an environment variable **`MCP_REQUEST_HEADERS`** (same name Webex uses for the header in **CustomHeaderAuth**):

- **Value** = the secret string Webex will send. The server expects an HTTP header named **`MCP_REQUEST_HEADERS`** with exactly that value on requests to **`/mcp`** (and any path other than **`GET /`** and **`GET /health`**).

**Multiple headers:** set the value to a JSON object, for example:

`{"X-My-Header": "token1", "X-Other": "token2"}`

Health checks do **not** send this header; **`/`** and **`/health`** stay unauthenticated so App Runner stays healthy.

## Files

| File | Role |
|------|------|
| `server.py` | MCP tools + `app` ASGI entrypoint + inline documentation |
| `requirements.txt` | Python dependencies |
| `start.sh` | App Runner **build**: install dependencies |
| `run.sh` | App Runner **start**: `uvicorn` on `$PORT` |
| `.gitattributes` | Shell scripts checked out with LF (Linux/App Runner) |
| `.gitignore` | Ignores venvs and caches |
