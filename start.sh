#!/bin/sh
# Railway startup script.
# 1. Restore the latest garmin.db from Cloudflare R2 (if available).
# 2. Start the MCP server under xvfb-run.

set -e

DB_PATH="${GARMIN_DATA_DIR:-/app/data}/garmin.db"
LITESTREAM_CONFIG="/app/litestream.yml"

echo "[start.sh] Restoring garmin.db from R2..."
if /usr/local/bin/litestream restore -if-replica-exists -config "$LITESTREAM_CONFIG" "$DB_PATH"; then
    echo "[start.sh] Restore complete: $DB_PATH"
else
    echo "[start.sh] No replica found or restore failed — starting with empty DB."
fi

echo "[start.sh] Starting MCP server..."
exec xvfb-run -a --auto-servernum --server-args='-screen 0 1920x1080x24' \
    python -u run_mcp.py
