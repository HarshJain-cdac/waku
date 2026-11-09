"""Wiring — builds one Waku from its parts. Gateways call `respond()`.

This file is the assembly diagram in code: config → db → tools → memory →
session → loop. If you want to understand the repo in one place, start here.
"""

from __future__ import annotations

from waku.config import Settings, load_settings
from waku.db import connect
from waku.loop.agent import LoopResult, Observer, run_loop
from waku.loop.models import get_client
from waku.ops.tracing import Tracer, compose
from waku.runtime.session import Session
from waku.tools import build_registry
from waku.tools import intent as intent_rules


class Waku:
    def __init__(self, settings: Settings | None = None, client=None, conn=None):
        # `client` and `conn` are injectable: evals swap in a scripted model,
        # the dashboard injects a cross-thread connection. Same seam either way.
        self.settings = settings or load_settings()
        self.settings.ensure_home()
        self.conn = conn or connect(self.settings.home)
        self.client = client or get_client(self.settings)

        # Memory first: the memory-management tools need it.
        from waku.memory import Memory

        self.memory = Memory(self.conn, self.settings, self.client)
        self.tools = build_registry(self.conn, self.settings, self.memory)
        self.mcp_bridge = getattr(self.tools, "mcp_bridge", None)
        self.session = Session(self.settings, memory=self.memory)
        self.tracer = Tracer(self.settings)
        # the domain check's model (waku/nam/domain.py), built on first use,
        # and the last turn's system prompt, for the check's second reply
        self._nam_domain = None
        self._last_system = ""

    def close(self) -> None:
        """Release external resources (MCP subprocesses). Called when the
        dashboard rebuilds the agent after a settings change."""
        if self.mcp_bridge is not None:
            self.mcp_bridge.close()

    def respond(self, user_message: str, observer: Observer | None = None,
                source: str = "cli", stream: bool = False, actor=None) -> LoopResult:
        """One full turn: assemble working memory → run the loop → persist.
        `source` tags which gateway the message arrived through (cli / voice /
        telegram / dashboard), so the unified chat can show its origin.
        `stream=True` streams the reply text token by token to the observer.
        Everything that happens is both shown (observer) and recorded (tracer).
        `actor` is the trusted identity context the caller was given
        (waku/nam/identity.py); None is this machine's own officer."""
        # capture the gate + graph decisions as they flow by, so we can persist
        # them with the turn (the reopened-thread telemetry the dashboard shows)
        import time
        captured: dict = {}

        def _capture(kind, ev):
            if kind == "gate":
                captured["gate"] = {"decision": ev.get("decision"), "reason": ev.get("reason")}
            if kind == "route":
                captured["graph_route"] = {"target": ev.get("target"), "reason": ev.get("reason")}
            if kind == "triage":
                captured["triage_reason"] = ev.get("reason")
            if kind == "graph_end":
                captured["graph_path"] = ev.get("path")
            if kind == "domain":
                captured["domain"] = {"domain": ev.get("domain"), "reason": ev.get("reason")}
        notify = compose(observer, self.tracer.event, _capture)
        t0 = time.perf_counter()
        # the chat this turn runs in, and who acts in it, for the NAM tools
        from contextlib import nullcontext

        from waku.nam import case, chatstate

        chat = chatstate.enter(self.session.session_id)
        try:
            with case.acting(actor) if actor is not None else nullcontext():
                return self._respond(user_message, source, stream, notify, captured, t0)
        finally:
            chatstate.leave(chat)

    def _respond(self, user_message: str, source: str, stream: bool, notify, captured: dict,
                 t0: float) -> LoopResult:
        import time

        with self.tracer.turn(user_message):
            # The graph front door is optional and can NEVER make Waku worse:
            # flag off → this is exactly the old code path; flag on → the triage
            # graph decides quick vs full, and any failure anywhere falls open
            # to the plain loop below (same fail-open rule as the retrieval gate).
            # THE INTENT NODE — what kind of message is this, decided before
            # anything reaches the network. It costs no model call (see
            # waku/tools/intent.py for why that is the point on this
            # deployment), and it is what the harness diagram's Intent box and
            # KG block light on.
            #
            # Only a confident greeting short-circuits. Everything else is
            # LABELLED and falls through untouched, so this node can remove
            # latency and can never remove capability.
            result = None
            in_conversation = any(m.get("role") == "assistant"
                                  for m in self.session.history[-2 * self.settings.history_turns:])
            intent, intent_reason = intent_rules.classify(user_message, in_conversation)
            notify("intent", {"intent": intent, "reason": intent_reason})
            captured["intent"] = {"intent": intent, "reason": intent_reason}

            # Not when the triage graph is on: that flag says "the graph is
            # this Waku's front door", and a router someone deliberately
            # enabled must not be pre-empted by a shortcut in front of it.
            # Flag off (the default) is where the shortcut earns its keep.
            if (intent == intent_rules.GREETING and self.settings.fast_greetings
                    and not self.settings.graph_workflows):
                reply_text = intent_rules.greeting_reply(user_message)
                if stream:
                    # Same event shape the loop streams, so every gateway
                    # renders it identically — it simply arrives all at once.
                    notify("text", {"delta": reply_text})
                result = LoopResult(reply=reply_text, tool_calls=[], iterations=0)

            if result is None and self.settings.graph_workflows:
                try:
                    result = self._respond_via_graph(user_message, notify, stream)
                except Exception as exc:
                    notify("graph_end", {"workflow": "triage", "ms": 0, "steps": 0,
                                         "path": [], "error": repr(exc)})
                    result = None
            if result is None:
                result = self._run_full_turn(user_message, notify, stream)
                # the agent stays on the work (waku/nam/domain.py): a reply that
                # answered something else from general knowledge is written again
                result = self._domain_review(user_message, result, notify)
                # a side question mid-case: its answer, then the case's open
                # question again with its checked options (waku/nam/stage_tools.py)
                self._nam_reminder(result, notify, stream)

            quick = captured.get("graph_route", {}).get("target") == "quick_reply"

            def _status(out: str) -> str:
                low = (out or "").lower()
                return "error" if ("failed" in low or "timed out" in low
                                   or low.startswith("error")) else "ok"
            meta = {
                "gate": captured.get("gate"),
                "domain": captured.get("domain"),
                "graph": ({"workflow": "triage",
                           "route": "quick" if quick else "full",
                           "reason": captured.get("triage_reason", ""),
                           "path": captured.get("graph_path")}
                          if "graph_route" in captured else None),
                "iterations": result.iterations,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "tools": [{"tool": c["tool"], "status": _status(c["output"])}
                          for c in result.tool_calls],
                # which brain answered this turn — so a reopened thread (or a
                # thread you switched models mid-way) shows it per card. A quick
                # graph turn was answered by the small model; say so honestly.
                "model": self.settings.small_model if quick else self.settings.model,
                "provider": self.settings.provider,
            }
            self.session.add_exchange(user_message, result.reply, tool_calls=result.tool_calls,
                                      source=source, meta=meta)
            if self.memory is not None:
                self.memory.maybe_consolidate(notify=notify)
                self.memory.export_markdown()   # keep MEMORY.md in sync

        self.tracer.end_turn(result.reply, result.iterations)
        return result

    def _domain_review(self, user_message: str, result: LoopResult, notify) -> LoopResult:
        """The turn's reply, or the agent's second reply when the check found
        the first answered a request that is not procurement work. The agent
        writes both; the harness only checks (waku/nam/domain.py)."""
        from waku.nam import domain

        if not domain.enabled(getattr(self.settings, "kg_url", ""),
                              getattr(self.settings, "domain_only", None)):
            return result
        try:
            if self._nam_domain is None:
                from waku.nam import llm as nam_llm

                self._nam_domain = nam_llm.client_asker(
                    getattr(self.memory, "client", None) or self.client, self.settings,
                    self.conn, "domain") or False
            verdict, why = domain.review(user_message, result.reply, result.tool_calls,
                                         self._nam_domain or None)
            notify("domain", {"domain": verdict, "reason": why})
            if verdict != domain.STRAYED or not self._last_system:
                return result
            window = self.settings.history_turns * 2
            messages = self.session.history[-window:] + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": result.reply},
                {"role": "user", "content": domain.REDO}]
            # not streamed: the screens replace the streamed text with the
            # turn's final reply
            again = run_loop(client=self.client, model=self.settings.model,
                             system=self._last_system, messages=messages, tools=self.tools,
                             max_iterations=self.settings.max_iterations,
                             max_tokens=self.settings.max_tokens, observer=notify,
                             stream=False)
        except Exception as exc:  # noqa: BLE001 - the check never loses a reply
            notify("domain", {"domain": "error", "reason": repr(exc)[:160]})
            return result
        if not (again.reply or "").strip():
            return result
        from waku.nam import answer_data

        again.reply = answer_data.complete(again.reply, again.tool_calls)
        again.iterations += result.iterations
        return again

    def _nam_reminder(self, result: LoopResult, notify, stream: bool) -> None:
        """Ask the case's open question again after a turn that asked nothing."""
        if any(c.get("tool") in ("nam_ask", "nam_choose", "ask_options") for c in result.tool_calls) or \
                "nam_ask" not in {t["name"] for t in self.tools.schemas()}:
            return
        from waku.nam import stage_tools

        try:
            back = stage_tools.reminder(self.conn, self.session.session_id)
        except Exception:  # noqa: BLE001 - a reminder is a courtesy, the reply stands
            return
        if back is None:
            return
        text, ask = back
        extra = f"\n\nBack to the need: {text}"
        result.reply = (result.reply or "") + extra
        result.tool_calls = [*result.tool_calls, {
            "tool": "ask_options", "args": ask,
            "output": f"Asked the user again: \"{text}\". Waiting for the answer."}]
        if stream:
            notify("text", {"delta": extra})
        notify("ask_options", ask)

    def _nam_guide(self) -> str | None:
        """The PR Creation Flow and this chat's case, for the agent's
        instructions (waku/nam/flow.py), or None where NAM is not set up.
        Never breaks a turn: an unreadable case is just the guide."""
        if not getattr(self.settings, "kg_url", "") or "nam_need" not in {
                t["name"] for t in self.tools.schemas()}:
            return None
        from waku.nam import case, chatstate, flow

        try:
            data = case.for_session(self.conn, self.session.session_id)
        except Exception:  # noqa: BLE001 - the guide stands without the case
            data = None
        # an open case's questions carry the records' options, never made-up
        # ones: the generic ask_options steps aside (waku/tools/clarify.py)
        chatstate.set_case_open(data is not None and flow.stage_of(data)[1] != "done")
        return flow.guide(data)

    def _run_full_turn(self, user_message: str, notify, stream: bool) -> LoopResult:
        """The classic turn: assemble working memory, run THE loop. Extracted
        verbatim so the graph's full_agent node calls the SAME code as the
        flag-off default — loop-as-a-node can never drift from loop-as-default."""
        # the PR Creation Flow and this chat's case are in view every turn: the
        # chat's memory of where the need stands (waku/nam/flow.py)
        self.session.nam_guide = self._nam_guide()
        system = self.session.build_system(user_message, notify=notify)
        self._last_system = system
        # Working memory is a bounded window: only the last N turns (2 rows
        # each) enter the prompt, so context/cost/latency stay flat no matter
        # how long the conversation runs. Older turns live in state.db and
        # come back via the retrieval gate + episodic memory when relevant.
        window = self.settings.history_turns * 2
        messages = self.session.history[-window:] + [{"role": "user", "content": user_message}]

        result = run_loop(
            client=self.client,
            model=self.settings.model,
            system=system,
            messages=messages,
            tools=self.tools,
            max_iterations=self.settings.max_iterations,
            max_tokens=self.settings.max_tokens,
            observer=notify,
            stream=stream,
        )
        # the KG data in the answer must not depend on which model wrote it
        # (waku/nam/answer_data.py): what the reply left out is added in code
        from waku.nam import answer_data

        result.reply = answer_data.complete(result.reply, result.tool_calls)
        return result

    def _respond_via_graph(self, user_message: str, notify, stream: bool) -> LoopResult | None:
        """One turn through the triage graph workflow. Returns None whenever
        the graph didn't produce an answer — respond() then falls open to the
        plain loop, so this path can only ever ADD speed, never lose a reply."""
        from waku.graph import run_graph
        from waku.graph.workflows.triage import (
            QUICK_REPLY_PROMPT,
            build_triage_graph,
            classify_message,
            todays_events,
        )

        def quick_reply(state: dict) -> str:
            prompt = QUICK_REPLY_PROMPT.format(calendar=state.get("calendar", ""),
                                               message=state["message"])
            response = self.client.messages.create(
                model=self.settings.small_model, max_tokens=600,
                messages=[{"role": "user", "content": prompt}])
            return "".join(b.text for b in response.content if b.type == "text")

        graph = build_triage_graph(
            classify_fn=lambda m: classify_message(self.client, self.settings.small_model, m),
            calendar_fn=lambda: todays_events(self.settings.home),
            quick_fn=quick_reply,
            # the full path is the SAME method the flag-off default runs; the
            # engine's tagged notifier stamps its inner events with node=
            full_fn=lambda state: self._run_full_turn(
                state["message"], state.get("_notify", notify), stream),
        )
        state = run_graph(graph, {"message": user_message}, observer=notify)
        if isinstance(state.get("result"), LoopResult):
            return state["result"]
        if state.get("reply"):
            return LoopResult(reply=state["reply"], tool_calls=[], iterations=1)
        return None  # graph produced nothing → caller falls open to the loop
