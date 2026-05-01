import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from garmin_mcp.server import mcp

app = FastAPI()

explicitly telling the app to trust the railway host
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

BASE_URL = "https://garmin-mcp-production-48d4.up.railway.app"

@app.get("/.well-known/oauth-authorization-server")
async def oauth_discovery():
    return JSONResponse({
        "issuer": BASE_URL,
        "authorization_endpoint": f"{BASE_URL}/oauth/authorize",
        "token_endpoint": f"{BASE_URL}/oauth/token",
        "registration_endpoint": f"{BASE_URL}/oauth/register",
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "mcp_sse_endpoint": f"{BASE_URL}/mcp/sse"
    })

@app.api_route("/oauth/authorize", methods=["GET", "POST"])
async def oauth_authorize(request: Request):
    state = request.query_params.get("state")
    redirect_uri = request.query_params.get("redirect_uri")
    if not redirect_uri:
        return JSONResponse({"error": "missing redirect_uri"}, status_code=400)return RedirectResponse(f"{redirect_uri}?code=dummy_code&state={state}")

@app.api_route("/oauth/token", methods=["POST"])
async def oauth_token(request: Request):
    return JSONResponse({
        "access_token": "dummy_access_token",
        "token_type": "bearer",
        "expires_in": 3600,
        "refresh_token": "dummy_refresh_token",
        "scope": "openid profile offline_access"
    })

@app.api_route("/oauth/register", methods=["GET", "POST"])
async def oauth_register(request: Request):
    return JSONResponse({
        "client_id": "dummy-client-id",
        "client_secret": "dummy-client-secret",
        "client_id_issued_at": 0,
        "token_endpoint_auth_method": "none",
        "redirect_uris": [f"{BASE_URL}/oauth/callback"]
    })

app.mount("/mcp", mcp.sse_app())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")