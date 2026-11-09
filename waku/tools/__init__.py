"""The agent's tools. Flagship-task tools (calendar/notes/messages), memory
self-management (manage_memory/update_soul/create_skill), and opt-in adapters:
Apple ecosystem (WAKU_APPLE_TOOLS=1) and MCP servers (.waku/mcp.json)."""

from __future__ import annotations

import sqlite3

from waku.config import Settings
from waku.tools import calendar, clarify, memory_admin, messages, notes, search
from waku.tools.registry import ToolRegistry


def build_registry(conn: sqlite3.Connection, settings: Settings, memory=None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        calendar.make_tool(
            conn,
            settings.home,
            apple_calendar=settings.apple_calendar,
            google_calendar=settings.google_calendar,
            google_calendar_id=settings.google_calendar_id,
        )
    )
    # Read side: "what's on my calendar?" — one tool across every connected
    # source (Google when signed in, plus waku's own), so the model never has
    # to guess which calendar the user meant.
    registry.register(calendar.make_list_tool(conn, settings.home))
    registry.register(notes.make_tool(conn))
    registry.register(messages.make_tool(settings.home))
    # Web search — pairs with create_event for the multi-tool loop demo
    # ("find the World Cup games left and add them to my calendar").
    registry.register(search.make_tool())
    # Clarify-before-acting: ask a fixed-choice question instead of guessing,
    # before an underspecified create/generate call.
    registry.register(clarify.make_tool())

    # NRL tender knowledge-graph precedent (read-only, over HTTP to the KG's
    # precedent_api service). Registered only when WAKU_KG_URL points somewhere:
    # a tool the model can see but never reach is worse than no tool, because it
    # will try, fail, and narrate the failure to the user mid-wizard.
    #
    # Reference material the model can be shown while deciding — read-only,
    # and deliberately not wired into any drafting flow. See
    # waku/nam/kg_tools.py.
    if getattr(settings, "kg_url", ""):
        from waku.nam import kg_tools as kg_precedent

        only = kg_precedent.allowed(getattr(settings, "kg_tools", ""))
        kg_api = kg_precedent.kg_api(getattr(settings, "kg_api_url", ""), settings.kg_url)
        for t in kg_precedent.make_tools(settings.kg_url, only, kg_api):
            registry.register(t)

        # NAM, the PR Creation Flow (waku/nam/flow.py): one tool per step, each
        # gate in code (waku/nam/stage_tools.py). A test of some KG tools alone
        # (WAKU_KG_TOOLS) leaves them out unless it names "nam".
        if only is None or "nam" in only:
            from waku.nam import stage_tools

            # the flow counts and narrows SAP's records; a PUR case's own data
            # that SAP does not show is the KG tools' (kg_tender_record)
            for t in stage_tools.make_tools(conn, settings.home, settings.kg_url):
                registry.register(t)

    # Memory self-management — the agent can correct/forget memory, learn rules,
    # and author its own skills (feels like a personal agent, not a black box).
    if memory is not None:
        registry.register(memory_admin.make_manage_memory_tool(memory))
        registry.register(memory_admin.make_update_soul_tool(settings))
        registry.register(memory_admin.make_create_skill_tool(settings, memory))

    # Experimental tools — off by default; opt in with WAKU_EXPERIMENTAL=1.
    # delegate_task (sub-agents via pi) is live; terminal/browser/cron are
    # still skeletons that report "coming soon".
    #
    # Trust settings.experimental ALONE. load_settings() already defaults it from
    # WAKU_EXPERIMENTAL, so re-checking the env here would let the global switch
    # override an explicit False — and the arena passes experimental=False for
    # every non-coding race. Once the dashboard could write WAKU_EXPERIMENTAL=1,
    # that OR silently forced delegate_task into races that never asked for it.
    if getattr(settings, "experimental", False):
        from waku.tools import experimental

        for t in experimental.make_tools(settings):
            registry.register(t)

    # Apple ecosystem readers/writers (opt-in; first use triggers macOS prompts).
    if settings.apple_tools:
        from waku.tools import apple

        for t in apple.make_tools():
            registry.register(t)

    # Read-only GitHub via the gh CLI (opt-in; uses gh's own auth, no token here).
    if getattr(settings, "gh_tool", False):
        from waku.tools import github

        registry.register(github.make_tool(default_repo=getattr(settings, "gh_repo", "")))

    # MCP servers (opt-in via .waku/mcp.json).
    mcp_config = settings.home / "mcp.json"
    if mcp_config.exists():
        try:
            from waku.tools.mcp_client import MCPBridge

            bridge = MCPBridge(mcp_config)
            for t in bridge.start():
                registry.register(t)
            registry.mcp_bridge = bridge  # so Waku.close() can stop the servers
        except ImportError:
            print("mcp.json found but the 'mcp' package is missing — pip install 'waku-agent[mcp]'")

    return registry