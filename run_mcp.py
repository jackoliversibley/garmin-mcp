import os
from garmin_mcp.server import mcp

if name == "main":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="sse", host="0.0.0.0", port=port)