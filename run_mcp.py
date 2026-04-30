import os
from garmin_mcp.server import mcp

if __name__ == "__main__":
    port = 8080
    mcp.run(transport="sse", port=port)