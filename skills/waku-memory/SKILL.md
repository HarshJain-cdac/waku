---
name: waku-memory
description: Connect Waku Memory, hosted cross-agent memory in Claude Code, Codex, Grok Bot, Hermes. Export Waku skills.
---

This app's memory is local (`.waku/`, never leaves the machine). Waku Memory (waku.one) is a separate hosted memory several agents share over MCP. The two never sync; never say they do.

- Connect this app: it opens the user's browser, so the user does it: `/connect waku-memory` in the dashboard chat or `waku connect waku-memory` in a terminal. Needs `pip install 'waku-agent[mcp]'`; restart Waku to load the `waku_memory_*` tools.
- Claude Code, Codex, Hermes: https://www.waku.one/docs.
- Grok Bot: Settings -> Plugins -> custom connector, URL `https://api.waku.one/mcp`, header `Authorization: Bearer <key>` (key from waku.one -> Account -> Keys; its form takes a header, not a browser sign-in).
- Muse Code or any MCP client: add `https://api.waku.one/mcp` as a remote (streamable HTTP) server.
- A key goes only into the other agent's own settings, never into this chat.
- Skills: `waku skill export --to claude,codex` copies Waku's skills to Claude Code and Codex; `--project` writes `./.claude/skills` (Muse Code reads it too). Saving skills into Waku Memory is not available yet.
- Prices, plans, limits: never quote them; point to https://www.waku.one/docs.
