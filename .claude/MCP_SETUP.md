# MCP Server Setup Log

---

## How to Add Any GitHub/npm MCP Server

Most MCP servers from GitHub are published to npm. The reliable pattern for adding them:

### Step 1 — Get the npm package name
Check the GitHub README for the npm package name (usually in the install instructions).

### Step 2 — Get any required API keys
Most servers need an API key. Get it from whatever service they document.

### Step 3 — Add via `claude mcp add --scope user`
```cmd
claude mcp add --scope user <server-name> -e KEY_NAME=<value> -- npx -y <npm-package-name>
```
- `--scope user` registers it globally in `~/.claude.json` so it works in all projects and worktrees
- `-e KEY=VALUE` sets environment variables the server needs
- `--` separates the claude args from the npx command

### Step 4 — Verify
```cmd
claude mcp list
```
Should show the server as `✓ Connected` after restarting Claude Code.

### What NOT to do
- Don't use `.mcp.json` unless you need project-specific config — it requires extra approval steps and can fail silently in worktrees
- Don't use `claude mcp add` without `--scope user` unless you're intentionally scoping to one project directory
- Don't follow GitHub READMEs that say `claude plugin add` — that command doesn't exist

---


## Stitch MCP (`@_davideast/stitch-mcp`)

### What it does
Proxies Firebase/Firestore data from the `reformai-stitch` Google Cloud project into Claude Code.

### Issues encountered during initial setup (2026-03-20)

#### 1. gcloud not installed
**Problem:** `winget install Google.CloudSDK` was required. gcloud was not present on the system at all.
**Fix:** Install Google Cloud SDK via winget or from cloud.google.com/sdk.

#### 2. gcloud not on PATH after install
**Problem:** Even after installing, `gcloud.cmd` was not on the Windows PATH. stitch internally calls `gcloud.cmd` to refresh tokens and silently fails if it can't find it.
**Fix:** Explicitly set `PATH` in `.mcp.json` env to include the gcloud bin directory:
```
C:\Users\cjlea\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin
```

#### 3. stitch uses its own isolated gcloud config — NOT system ADC
**Problem:** stitch does not use your normal `gcloud auth application-default login` credentials. It uses a separate config directory at `C:\Users\cjlea\.stitch-mcp\config`. Running `gcloud auth application-default login` normally does nothing for stitch.
**Fix:** Authenticate specifically for stitch using:
```cmd
set "CLOUDSDK_CONFIG=C:\Users\cjlea\.stitch-mcp\config" && gcloud auth application-default login
```
This must be re-run if credentials expire.

#### 4. `CLOUDSDK_CONFIG` not set in `.mcp.json`
**Problem:** stitch couldn't find its credentials because `CLOUDSDK_CONFIG` wasn't passed as an env var.
**Fix:** Added `CLOUDSDK_CONFIG` to the env block in `.mcp.json`.

#### 5. `.mcp.json` only existed in the worktree, not the main repo root
**Problem:** Claude Code looks for `.mcp.json` relative to the project root, not just the worktree.
**Fix:** Added `.mcp.json` to both the main repo root (`agent-oversight/.mcp.json`) and the worktree.

#### 6. `enabledMcpjsonServers` not set in global settings
**Problem:** Claude Code requires explicit approval of MCP servers from `.mcp.json`. Without this, the server is loaded but not approved.
**Fix:** Added to `~/.claude/settings.json`:
```json
"enabledMcpjsonServers": ["stitch"]
```

---

### Final working `.mcp.json`
Located at repo root (`agent-oversight/.mcp.json`) and the worktree:
```json
{
  "mcpServers": {
    "stitch": {
      "command": "npx",
      "args": ["-y", "@_davideast/stitch-mcp", "proxy"],
      "env": {
        "GOOGLE_CLOUD_PROJECT": "reformai-stitch",
        "CLOUDSDK_CONFIG": "C:\\Users\\cjlea\\.stitch-mcp\\config",
        "PATH": "C:\\Users\\cjlea\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\nodejs;C:\\WINDOWS\\system32;C:\\WINDOWS;C:\\Users\\cjlea\\AppData\\Roaming\\npm"
      }
    }
  }
}
```

### Re-authentication (when credentials expire)
Run in cmd (not bash):
```cmd
set "CLOUDSDK_CONFIG=C:\Users\cjlea\.stitch-mcp\config" && gcloud auth application-default login
```
Then restart Claude Code.

---

## Nano Banana 2 MCP (`nano-banana-2-mcp`)

### What it does
Generates and edits images using Google's Gemini 3.1 Flash Image model (aka "nano banana 2").

### Issues encountered during initial setup (2026-03-20)

#### 1. `claude plugin add` doesn't exist
**Problem:** Tried `claude plugin add nano-banana-2-mcp` based on community docs — command doesn't exist in this version of Claude Code.
**Outcome:** Error: `unknown command 'add'`
**Fix:** Add via `.mcp.json` or `claude mcp add` instead.

#### 2. Added to `.mcp.json` but didn't load
**Problem:** Added to `.mcp.json` with `enabledMcpjsonServers` in global settings, but tools never appeared.
**Outcome:** Multiple restarts, still not loading.
**Root cause:** `ToolSearch` doesn't surface MCP tools from `.mcp.json` reliably in worktree sessions.

#### 3. `claude mcp add` registered under wrong project
**Problem:** Running `claude mcp add nano-banana-2 ...` from `C:\Users\cjlea` registered the server under that directory as a "project", not globally. The worktree session couldn't see it.
**Outcome:** `claude mcp list` showed no servers; server not available.
**Fix:** Use `--scope user` flag to register at user level:
```cmd
claude mcp add --scope user nano-banana-2 -e GEMINI_API_KEY=<key> -- npx -y nano-banana-2-mcp
```

### Final working setup
Registered via `claude mcp add --scope user` in `~/.claude.json` top-level `mcpServers`. Confirmed connected via `claude mcp list`.

### Key lesson
For MCP servers that don't need project-specific config, always use `--scope user` with `claude mcp add`. Avoids the `.mcp.json` approval dance entirely.

---

## Magic MCP (`@21st-dev/magic`)

### What it does
Generates polished, production-ready React UI components from natural language descriptions. Invoked with `/ui` in Claude Code chat. Components are inspired by the 21st.dev component library.

**GitHub:** https://github.com/21st-dev/magic-mcp

### Setup

#### 1. Get API key
Go to https://21st.dev/magic/console and generate an API key.

#### 2. Add via claude mcp add
```cmd
claude mcp add --scope user magic -e API_KEY=<your-key> -- npx -y @21st-dev/magic@latest
```

#### 3. Verify
```cmd
claude mcp list
```

### Usage
In Claude Code chat, describe a UI component and prefix with `/ui`:
```
/ui a card component with a user avatar, name, and follow button
```
