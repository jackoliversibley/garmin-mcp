import os
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from garmin_mcp.server import mcp

app = FastAPI()

@app.get("/.well-known/oauth-authorization-server")
async def oauth_discovery():
    return JSONResponse({
        "issuer": "https://garmin-mcp-production-48d4.up.railway.app",
        "authorization_endpoint": "https://garmin-mcp-production-48d4.up.railway.app/oauth/authorize",
        "token_endpoint": "https://garmin-mcp-production-48d4.up.railway.app/oauth/token",
        "registration_endpoint": "https://garmin-mcp-production-48d4.up.railway.app/oauth/register",
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"]
    })

app.mount("/", mcp.sse_app())

if __name__ == "__main__":
    port = 8080
    uvicorn.run(app, host="0.0.0.0", port=port)