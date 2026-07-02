# Windows PowerShell helper script to start MCP Inspector against the lab server
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerPath = Join-Path $ScriptDir "implementation\mcp_server.py"

Write-Host "Launching @modelcontextprotocol/inspector against $ServerPath..." -ForegroundColor Cyan
npx -y @modelcontextprotocol/inspector python $ServerPath
