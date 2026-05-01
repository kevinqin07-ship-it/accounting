---
description: Configure the Composio connection so Claude Code can act on 500+ third-party apps (Gmail, Slack, Linear, GitHub, Notion, etc.)
argument-hint: "[app-name]"
allowed-tools: Bash Read Write WebFetch
---

# Connect Apps — Setup

Walk the user through getting Composio wired into this Claude Code session.

## Context

The plugin ships an MCP server entry that runs `npx -y @composio/mcp@latest start`
with `COMPOSIO_API_KEY` injected from `userConfig.composio_api_key` (see
`${CLAUDE_PLUGIN_ROOT}/.mcp.json`). The user's job in `/connect-apps:setup`
is to:

1. Make sure they have a Composio API key.
2. Confirm the MCP server can start.
3. Authorize the specific app(s) they want to use.

## Inputs

- `$ARGUMENTS` — optional app slug the user wants to connect immediately
  (e.g. `gmail`, `slack`, `github`, `linear`, `notion`).

## Steps

1. **Check prerequisites.** Verify `node` and `npx` are on PATH; if not, tell
   the user to install Node.js 18+ and stop.

   !`node --version 2>/dev/null && npx --version 2>/dev/null || echo "MISSING_NODE"`

2. **API key.** If the `composio_api_key` user-config value is unset, point
   the user to https://app.composio.dev/settings, ask them to paste a key,
   and remind them it is stored as a sensitive plugin config (not committed).
   Do not echo the key back.

3. **Smoke-test the MCP server.** Tell the user to reload the session (or run
   `/mcp`) so the `composio` server entry initializes. Confirm it shows up as
   connected in `/mcp` output.

4. **Connect an app.** If `$ARGUMENTS` is non-empty, use the Composio MCP
   tools (e.g. `composio.initiate_connection` / `composio.get_auth_url`) to
   start the OAuth flow for that app, print the consent URL, and wait for
   the user to confirm completion. Otherwise list the most common apps
   (Gmail, Slack, GitHub, Linear, Notion, Google Calendar, Jira, HubSpot)
   and ask which one to connect first.

5. **Verify.** Once connected, call a low-impact read action for the chosen
   app (e.g. `gmail.list_labels`, `slack.list_channels`, `github.get_me`) and
   show the user the result so they know it works.

## Notes

- Never write the API key to disk outside the plugin's user config.
- If multiple apps are requested, connect them one at a time so OAuth
  redirects don't collide.
- For headless environments (no browser), surface Composio's device-code
  flow instead of the OAuth redirect.
