import inspect
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from garmin_mcp.server import mcp
from mcp.server.sse import SseServerTransport
from mcp.server.transport_security import TransportSecuritySettings

logger = logging.getLogger("uvicorn.error")
BASE_URL = "https://garmin-mcp-production-48d4.up.railway.app"
RAILWAY_HOST = "garmin-mcp-production-48d4.up.railway.app"

sse = SseServerTransport(
    "/messages",
    security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


async def _get_tool_names():
    list_tools = getattr(mcp._mcp_server, "list_tools", None)
    if list_tools is None or not callable(list_tools):
        raise TypeError(f"list_tools is not callable: {type(list_tools)!r}")

    try:
        result = list_tools()
    except TypeError:
        # Some runtimes may expose list_tools as an async function requiring direct await.
        result = list_tools

    if inspect.isawaitable(result):
        result = await result
    elif inspect.iscoroutinefunction(result):
        result = await result()

    if inspect.isfunction(result):
        raise TypeError(f"list_tools returned a function instead of tool data: {result!r}")

    return [tool.name for tool in result]


@asynccontextmanager
async def lifespan(app: FastAPI):
    route_specs = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = sorted(getattr(route, "methods", []) or [])
        if path:
            route_specs.append(f"{path} [{', '.join(methods)}]")

    logger.info("starting uvicorn on 0.0.0.0:%s", os.environ.get("PORT", "8080"))
    try:
        tool_names = await _get_tool_names()
        logger.info("registered MCP tools: %s", tool_names)
    except Exception:
        logger.exception("startup tool verification failed; continuing without tool list")
    logger.info("registered FastAPI routes: %s", route_specs)
    yield


app = FastAPI(lifespan=lifespan)

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


@app.get("/sse")
async def sse_endpoint(request: Request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp._mcp_server.run(
            streams[0],
            streams[1],
            mcp._mcp_server.create_initialization_options(),
        )
    return Response()


@app.post("/messages")
@app.post("/messages/")
async def message_endpoint(request: Request):
    try:
        await sse.handle_post_message(request.scope, request.receive, request._send)
        return Response()
    except Exception:
        logger.exception("failed handling MCP message POST")
        return JSONResponse({"error": "failed handling MCP message POST"}, status_code=500)


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
