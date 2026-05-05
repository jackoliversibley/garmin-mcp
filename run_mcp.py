import inspect
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from garmin_mcp.server import mcp

logger = logging.getLogger("uvicorn.error")
BASE_URL = "https://garmin-mcp-production-48d4.up.railway.app"
RAILWAY_HOST = "garmin-mcp-production-48d4.up.railway.app"


def _build_tool_names():
    list_tools = getattr(mcp._mcp_server, "list_tools", None)
    if list_tools is None or not callable(list_tools):
        raise TypeError(f"list_tools is not callable: {type(list_tools)!r}")

    result = list_tools()
    if inspect.isawaitable(result):
        return result
    return result


@asynccontextmanager
async def lifespan(app):
    route_specs = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = sorted(getattr(route, "methods", []) or [])
        if path:
            route_specs.append(f"{path} [{', '.join(methods)}]")

    logger.info("starting uvicorn on 0.0.0.0:%s", os.environ.get("PORT", "8080"))
    try:
        tools_result = _build_tool_names()
        tools = await tools_result if inspect.isawaitable(tools_result) else tools_result
        tool_names = [tool.name for tool in tools]
        logger.info("registered MCP tools: %s", tool_names)
    except Exception:
        logger.exception("startup tool verification failed; continuing without tool list")
    logger.info("registered FastAPI routes: %s", route_specs)
    yield


app = mcp.sse_app()
app.router.lifespan_context = lifespan

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        RAILWAY_HOST,
        "*.up.railway.app",
        "localhost",
        "127.0.0.1",
        "[::1]",
    ],
)


@app.get("/.well-known/oauth-authorization-server")
async def oauth_discovery():
    return JSONResponse(
        {
            "issuer": BASE_URL,
            "authorization_endpoint": f"{BASE_URL}/oauth/authorize",
            "token_endpoint": f"{BASE_URL}/oauth/token",
            "registration_endpoint": f"{BASE_URL}/oauth/register",
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "mcp_sse_endpoint": f"{BASE_URL}/sse",
        }
    )


@app.api_route("/oauth/authorize", methods=["GET", "POST"])
async def oauth_authorize(request: Request):
    state = request.query_params.get("state")
    redirect_uri = request.query_params.get("redirect_uri")
    if not redirect_uri:
        return JSONResponse({"error": "missing redirect_uri"}, status_code=400)
    return RedirectResponse(f"{redirect_uri}?code=dummy_code&state={state}")


@app.api_route("/oauth/token", methods=["POST"])
async def oauth_token(request: Request):
    return JSONResponse(
        {
            "access_token": "dummy_access_token",
            "token_type": "bearer",
            "expires_in": 3600,
            "refresh_token": "dummy_refresh_token",
            "scope": "openid profile offline_access",
        }
    )


@app.api_route("/oauth/register", methods=["GET", "POST"])
async def oauth_register(request: Request):
    return JSONResponse(
        {
            "client_id": "dummy-client-id",
            "client_secret": "dummy-client-secret",
            "client_id_issued_at": 0,
            "token_endpoint_auth_method": "none",
            "redirect_uris": [f"{BASE_URL}/oauth/callback"],
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("starting uvicorn on 0.0.0.0:%s", port)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level="info",
    )
