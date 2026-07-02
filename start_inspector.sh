#!/usr/bin/env bash
# Linux/macOS helper script to start MCP Inspector against the lab server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_PATH="$SCRIPT_DIR/implementation/mcp_server.py"

echo "Launching @modelcontextprotocol/inspector against $SERVER_PATH..."
mkdir -p .npm-cache
NPM_CONFIG_CACHE="$PWD/.npm-cache" npx -y @modelcontextprotocol/inspector python "$SERVER_PATH"
