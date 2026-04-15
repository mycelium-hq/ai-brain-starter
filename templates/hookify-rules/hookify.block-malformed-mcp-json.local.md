---
name: block-malformed-mcp-json
enabled: true
event: file
action: block
conditions:
  - field: file_path
    operator: regex_match
    pattern: \.mcp\.json$
  - field: new_text
    operator: regex_not_match
    pattern: ^\s*\{[\s\S]*\}\s*$
---

**`.mcp.json` content does not look like a complete JSON object.** Claude Code silently drops malformed MCP config files: every MCP server inside the file will stop loading with no warning. Common cause: orphaned blocks, stray braces, or content added outside the top-level `mcpServers` object. Fix the JSON structure (must open with `{` and close with matching `}`) before saving. Validate with `python3 -c "import json; json.load(open('<path>'))"`
