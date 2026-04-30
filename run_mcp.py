import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from garmin_mcp.server import mcp

app = FastAPI()

BASE_URL = "https://garmin-mcp-production-48d4.up.railway.app"

@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server():
    return JSONResponse(
        {
            "issuer": BASE_URL,
            "authorization_endpoint": f"{BASE_URL}/oauth/authorize",
            "token_endpoint": f"{BASE_URL}/oauth/token",
            "registration_endpoint": f"{BASE_URL}/oauth/register",
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_basic", "client_secret_post"],
            "scopes_supported": ["openid", "profile", "offline_access"],
        }
    )

@app.api_route("/oauth/authorize", methods=["GET", "POST"])
async def oauth_authorize(request: Request):
    return JSONResponse(
        {
            "ok": True,
            "message": "dummy authorization endpoint",
            "issuer": BASE_URL,
            
"authorization_endpoint": f"{BASE_URL}/oauth/authorize",
            "next": "Poke can continue the handshake with this response.",
        }
    )

@app.api_route("/oauth/token", methods=["POST"])
async def oauth_token(request: Request):
    return JSONResponse(
        {
            "access_token": "dummy-access-token",
            "token_type": "bearer",
            "expires_in": 3600,
            "refresh_token": "dummy-refresh-token",
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
            "redirect_uris": [f"{BASE_URL}/oauth/callback"],app.mount("/", mcp.sse_app())

if __name__ == "__main__":
    port = 8080
    uvicorn.run(app, host="0.0.0.0", port=port)