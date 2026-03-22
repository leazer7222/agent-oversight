# Context Agent

The Context Agent is responsible for surfacing relevant documentation and background information for any given task. It connects to the company's Google Drive via the `gdrive` MCP server.

## Capabilities
- List files in specific project folders.
- Search for documents by keyword or content.
- Read document contents to provide context to orchestrators or other sub-agents.

## Dependencies
- `gdrive` MCP server (must be configured in `.mcp.json` or `~/.claude.json`).
- Python SDK (`oversight.py`).
