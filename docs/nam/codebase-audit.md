# Waku codebase audit (Step 2)

Read-only audit of `waku-agent` as it stands on 2026-09-29, done before any NAM harness work.
References are `file:line`. The ratings are:
- **solid**: tested and fit for reuse.
- **partial**: works, but has gaps.
- **weak**: exists, but is not fit for the NAM API.
- **absent**: does not exist.

## 0. Scope

This work makes **Waku a strong harness for the NAM domain**, and most testing runs on Waku itself. A full product backend is not the goal.
- **In scope:**
  - the agent loop and orchestration
  - playbooks and routing
  - tools (schemas, validation, audit)
  - the Need Record state
  - document handling
  - guardrails and injection defense
  - model routing
  - evals
  - the harness's own entry point and its own security (identity passed in, role checks, isolation)
- **Out of scope:**
  - the NAM product backend and UI
  - live SAP and Aarohan connectors (future work; the KG serves the same data contracts now)
  - the dashboard's admin and benchmark routes
  - the nit-forge-ui wiring

  Items in these areas are marked *(out of scope)* below. They are listed only because they affect how the harness is tested.

## 1. Summary

The core is small and readable, with good seams for testing: the model and the DB can be injected, and there are 84 offline test files. The NAM code built so far holds to the FRS rules in code: the officer selects the precedent, nothing is invented, and model questions are checked. That covers only need capture, follow-up questions, similar cases and selection. Everything from references onwards is absent.

The harness is not yet fit to be called by a backend:
- There is no tenant, user or role model.
- One global agent sits behind one lock.
- Tool inputs and final outputs are not validated against any schema.
- There is no audit log.
- Auth is optional and CORS is `*`.
- Documents cannot be uploaded, and no state has history.

## 2. Agent loop and orchestration

| Item | Where | State |
|---|---|---|
| Loop: up to `WAKU_MAX_ITERATIONS` (10) turns, tools run one after another, stops when the model calls no tool | `waku/loop/agent.py:63-113` | partial |
| Tool errors go back to the model as text, with no `is_error` flag; LLM errors are not caught | `waku/tools/registry.py:57`, `agent.py` | weak |
| `stop_reason` (max_tokens, refusal) ignored, so truncated replies are returned as if final | `agent.py` | weak |
| Streaming falls back to non-streaming on any error, which can duplicate output | `agent.py:68-78` | weak |
| Structured / JSON-schema final output | none; internal JSON is parsed by slicing between braces (`retrieval_gate.py:52`, `consolidation.py:67`) | absent |
| Observer events (llm, tool, text, gate, route, graph_*) | `agent.py`, `app.py` | solid |
| Graph engine: waves, code routers, `max_visits`, `max_steps=25`, `on_error` | `waku/graph/engine.py` (14 tests) | solid |
| Graph checkpoint, resume, human-approval interrupts, stage gates | none | absent |
| Declarative question-flow engine (`mandatory_if`, `na_if`) | `waku/tools/flow_engine.py` | partial, reusable for FRS forms |

## 3. Models

- There are 11 providers: Anthropic-wire ones plus OpenAI-compatible ones via `OpenAICompatClient` (`waku/loop/models.py:80-164, 319+`). vLLM is reached through `WAKU_BASE_URL`, and there is a recovery path for tool calls the model writes as text (`models.py:269-316`). **solid**
- Routing is two-tier only: `model` for the loop and `small_model` for the gate, consolidation and triage. There is no per-task or per-tenant routing. **absent**
- There is no provider fallback, and retries are left to the SDK defaults. Timeout is `WAKU_LLM_TIMEOUT`, 120s (`models.py:241`). **weak**
- `nam_followup.model_asker` calls the private methods `client._call` and `_to_openai` (`nam_followup.py:465-480`), which ties it to the adapter's internals. **weak**
- `load_settings()` finds `.env` through `find_dotenv(usecwd=True)`, so which config loads depends on the working directory (`config.py:13-41`). This caused the earlier "claude sonnet" incident. **weak**

## 4. Tool layer

| Item | Where | State |
|---|---|---|
| `Tool(name, description, input_schema, fn -> str)` | `registry.py:15-34` | partial |
| Input validated against the schema before running | calls `tool.fn(**args)` directly (`registry.py:56`) | absent |
| Output schema | every tool returns a free string | absent |
| Retries, idempotency keys, side-effect classes (read / write / irreversible), per-tool timeouts | only a few tools have their own timeouts | absent |
| Permission and approval gates | none | absent |
| Audit of tool calls | trace events plus a `[tools used: ...]` line added to chat history (`session.py:145-157`) | weak |
| Tools registered depending on env flags | `waku/tools/__init__.py:14-110` | solid |
| `update_soul` and `create_skill` let the model rewrite its own prompts | `memory_admin.py:85-100` | risk |
| The session prompt names `update_nit_draft`, which is never registered | `waku/runtime/session.py:125-130` | stale |

## 5. State, sessions, memory

- **DB:** SQLite `.waku/state.db`, `busy_timeout=3000`, WAL not set (`waku/db.py:94-103`). Tables: `calendar_events`, `facts` + `facts_fts`, `episodes` + `episodes_fts`, `chat_log` (`db.py:12-91`).
- **Session:** only a `session_id` label on `chat_log`, supplied by the caller. The agent is process-wide, and `session.switch()` changes the shared object behind `agent_lock` (`waku/ops/browser_agent.py:39`). **weak** for multi-tenant use.
- **Memory:** facts (FTS5 BM25, with pluggable stores and a 14-test conformance suite) and episodes. **solid** as a component.
- **Consolidation leaks across users:** consolidation distils unconsolidated chat from **every** session into one shared pool (`waku/memory/consolidation.py:46-81`). **risk**
- **Instructions:** one global `SOUL.md` that mixes personal-assistant text with NRL rules (`session.py:15-98`). Skills are matched by keyword overlap, at least 2 words, 2 skills at most (`procedural/loader.py:77-91`). **weak** for per-flow playbooks.

## 6. API surface (`waku/ops/dashboard.py`, the harness's dev server; its admin routes are *(out of scope)*)

- **Server:** stdlib `ThreadingHTTPServer` on `WAKU_DASHBOARD_HOST` (default 127.0.0.1), port 7777 (`:32, :1535-1567`). Starting it also starts the Telegram, Discord and WhatsApp gateways. There is no access log (`:1528`).
- **Routes:** chat (`/api/chat`, `/api/chat/stream`), dashboard data, memory, SOUL and skill editing, `.env` writes (`/api/settings`, `/api/providers`, `/api/connections`), a read-only SQL console (`/api/query`), benchmarks, tender archive files, and the NAM routes.
- **NAM routes:**
  - GET `/api/nam/needs|dossier|need` (`:1166-1200`)
  - POST `/api/nam/need|capture|classify|similar|update|reference|replicate|case|compare|material|select` (`:1238-1370`)
- **No contract:** there is no versioned request or response contract, no OpenAPI, and no "messages + system" entry point. **absent**
- **Errors:** almost always HTTP 200 with `{"error": "<Type>: msg"}`, which leaks exception text. The NAM `reply()` ignores its `code` argument (`:1246-1247`). **weak**
- **Input handling:**
  - There is no body size limit; the server trusts the `Content-Length` header (`:1226`).
  - A `json.loads` failure drops the connection without a response (`:1241, :1374, :1500`).
  - `apply_provider(**payload)` passes the request body straight into keyword arguments (`:1521`).
  - **weak**
- **Concurrency:** only `capture` takes `agent_lock`. The other NAM writes share `agent.conn` with `check_same_thread=False` and take no lock. **weak**
- **UI mismatch** *(out of scope)*: the UI config still expects `/api/nit/*`, `/api/answer` and `/api/action` (`nit-forge-ui/src/config.ts:25-39`), and none of them exist. **stale**

## 7. Security

| Item | State |
|---|---|
| **Auth:** one optional shared bearer, `WAKU_DASHBOARD_KEY`, compared in constant time (`hmac.compare_digest` in `Handler._authorized`). Off in this deployment, and the UIs do not send one | none: anyone on the network has full access; per-user identity comes from the platform (D4) |
| **Tenants, users, roles, ownership:** none. Need ids (`NAM-YYYY-NNNN`, count-based) are guessable, and anyone can read or change any need | absent |
| **CORS:** `*`, with no Origin or Host check (`:100, :1003-1015`). An open browser tab could rewrite `.env` or the provider `base_url`, or turn on experimental code execution (`delegate_task`) | risk |
| **Admin and NAM routes share one surface,** with no separation *(out of scope; the harness entry point stays separate)* | risk |
| **Rate limiting and socket timeouts:** none (only Discord has a `TurnBudget`) | absent |
| **Secrets:** loaded from env or dotenv; only the last 4 characters are shown; `_safe_error` and `safe_exception` redact errors. But an unauthenticated `/api/providers` call can redirect a key to another host | partial |
| **Prompt-injection defense:** none, apart from one line in the follow-up prompt ("tender text is data", `nam_followup.py:310`). KG text, web, mail and MCP output reach the model unwrapped | absent |
| **Audit trail (who did what):** none. `chat_log` has no actor, traces have no request or tenant id, and `nam_needs` is overwritten in place | absent |
| **Reusable pieces:** the WhatsApp HMAC check (`compare_digest`, `whatsapp.py:187-191`), path confinement in `tender_archive.py` / `_serve_static` / `reveal_path`, and the error redactors | solid |

## 8. Observability

- **Traces:** JSONL at `.waku/traces/<date>.jsonl`, a `usage.jsonl` token ledger, optional OTel (`waku/ops/tracing.py`). **partial**
- **Gaps:**
  - Records carry no session, tenant or request id.
  - The file date is fixed when the tracer starts (`tracing.py:63`), so a long-running server never rolls over to a new day's file.
  - The OTel spans have zero duration.
- **Per-turn meta:** gate, latency and tools are stored in `chat_log.meta` (`app.py:111-131`).

## 9. NAM code built so far

| Module | What it does | State |
|---|---|---|
| `waku/tools/nam.py` (798) | Rule-based `classify` with `basis` / `confident` (tender type is never confident); `NeedRecord`; `similar_cases` with an explained `match_strength`; `compare`, `case_detail`, `lookup_reference` (SAP numbers get "not connected"; ambiguous matches are never auto-opened); `replicate`; `selected_material` (reads only `selected_cases`, with attribution and dedupe); `apply_update` against closed vocabularies | solid |
| `nam_capture.py` (579) | Parallel KG scan (lexical, semantic, health); sorts tenders into direct / line items / incidental; readiness; `capture()` pipeline; chat tool `nam_capture_need`; degrades when one lane is down | solid |
| `nam_followup.py` (541) | The model writes each question; the harness recounts the options against the tenders; coverage of at least 1/3, balance, retry once, no retry on outage; deterministic fallback on tender facets; at most 5 questions | solid (fragile model coupling) |
| `nam_dossier.py` (80) | Section-marked `.waku/nam/<ID>.md`; the id is validated, so no path traversal. Only `capture` writes | partial |
| `kg_precedent.py` (339) | 4 read-only KG chat tools; keeps "unavailable" separate from "no precedent"; tells the model not to invent rates or clauses | solid |
| `tender_archive.py` (140) | Serves archived notices, confined to the corpus, 64 MB cap | solid |
| `aan_reader.py` (270) | Reads text from PDF (pypdf, no OCR), DOCX (paragraphs and tables) and XLSX (openpyxl); deterministic `extract_fields`. **Nothing calls it**: the upload route is gone | orphaned |

**NAM state**
- **Storage:** one `nam_needs` table (`need_id`, `session_id`, `record_json`, `updated_at`), created lazily at call sites and not in `db.py`, with no migrations (`nam.py:478`).
- **No history or scoping:** writes are upserts, so there is no history. `session_id` is stored but never filtered on.
- **Id races:** ids are count-based (`nam.py:209`), so two calls at once can get the same id.
- **Two lifecycles** write the same stage field: capture then references, and similar then matching then selected.
- **Four copies of the truth:**
  1. the DB JSON
  2. the dossier `.md`
  3. the UI's localStorage `procurix.nam-case.v1`
  4. the NIT hand-off in localStorage
- **`nit_drafts`:** that table no longer exists.

**NAM pipeline coverage**

| Stage | State |
|---|---|
| Need capture, classification, follow-up questions | present |
| Similar cases, compare, reference lookup, replicate | present |
| Officer selection gate, selected-material merge | present |
| KG price and clause lookup (chat tools) | present |
| References step | partial (a stage and a dossier slot) |
| Guided form | absent |
| Quantity | absent |
| Estimate engine (Same / Similar / Derived, VARN / CAGR, wage and works) | absent |
| Basis of estimate | absent |
| Document generation (BOQ / SOR / SCC / PQC / spec / SOW / AAN) | absent |
| PR creation | absent |
| Checker / validation | absent |
| Freeze and package | absent |
| Approvals (Aarohan or DoA) | absent |
| NIT routing | absent |
| Re-upload and versioning | absent |
| Tracking | absent |
| Audit | absent |

SAP and Aarohan are not connected. The NIT wizard (`nit_flows.py`, `start_nit_flow` / `advance_nit_flow`, `update_nit_draft`) is referenced in code, docs, the UI and one test, but is missing from the tree.

**Guardrails in code (present)**
- Generation reads only `selected_cases`.
- Ambiguous references are never auto-opened.
- Tender type is never confident.
- Closed vocabularies are enforced.
- "KG unavailable" is kept separate from "no precedent".
- Model questions are recounted against real tenders.
- Archive paths are confined to the corpus.

**Guardrails (absent)**
- A duplicate need or PR check.
- A check that `/select` keys are in `related_cases`.
- A no-invented-rate check in code; today it is prompt-only.
- Holding irreversible actions until confirmed.

## 10. Documents

| Capability | PDF | DOCX | XLSX | Images |
|---|---|---|---|---|
| Parse text | pypdf (no OCR, no tables) | yes, including tables | yes | no |
| Upload endpoint | none | none | none | none |
| Storage, view, version, history, delete | none | none | none | none |
| Generate or export | none | none | none | n/a |
| Treated as untrusted | no | no | no | no |

The parsing libraries are an optional extra, `[nit]` (python-docx, openpyxl, pypdf). `.doc` gets a clear "re-save as .docx" error.

## 11. Tests

- **NAM:**
  - `test_nam.py` (about 40): classify, selection gate, attribution, `apply_update`, vocabulary sync with the UI.
  - `test_nam_capture.py` (9).
  - `test_nam_followup.py` (20): including retry, outage, and the injection framing.
  - `test_tender_archive.py` (8).
  - All run offline with stubs; 87 NAM tests pass.
- **Core:** graph engine, providers, memory store conformance, sessions, skills, tracing.
- **Broken:** `test_aan_extraction.py` imports `_extract_fields`, `_extract_text` and `waku.tools.nit_flows`, none of which exist. The full suite also has 20 failures that predate this work.
- **Not covered:**
  - the dashboard HTTP routes
  - kg_precedent's output formatting
  - the loop iteration limit and truncation
  - the stream fallback
  - any security behaviour

## 12. Harness priorities (what matters for a strong Waku)

1. **Contract:** the loop returns structured output that has been checked against a schema. Truncation and refusals are handled, and errors come back as typed results.
2. **Tools:** inputs and outputs are validated against their schemas. Each tool has a side-effect class (read / write / irreversible), retries and idempotency, and every call is written to an audit record.
3. **Orchestration:** a durable, staged NAM flow built on the graph engine, with checkpoints, gates and human-approval interrupts. Code picks the next step.
4. **Routing:** a per-FRS-function playbook replaces the global SOUL.md and keyword-matched skills.
5. **Need Record:** one versioned record per case with history, replacing the four copies.
6. **Documents:** ingest, version and parse documents inside the harness, with OCR for images. The parsed text is marked untrusted.
7. **Injection:** every untrusted text (documents, KG, web, MCP) is isolated before it reaches the model.
8. **Identity:** tenant, user and role come in on every call, and the harness enforces them. There is no memory or consolidation shared across users. The harness does not run a user system of its own.
9. **Models:** routing per task, a fallback, and a stable public call (no private `_call`).
10. **Evals:** every item above gets a deterministic eval that runs on Waku alone, with the model and KG scripted.

Dashboard hardening (CORS, admin routes, body limits) matters only as far as the harness entry point reuses that code *(out of scope otherwise)*.

## 13. What to reuse vs replace

**Reuse:**
- the NAM domain modules (`nam.py`, `nam_capture.py`, `nam_followup.py`, `kg_precedent.py`, `tender_archive.py`)
- `aan_reader` for parsing
- `flow_engine` for FRS form logic
- the graph engine as the base for staged flows
- the provider layer
- the error redactors
- the HMAC and path-confinement patterns
- the tracing JSONL writer as the base for an audit sink

**Replace or add:**
- a harness entry point (messages + short system prompt → schema-valid result) with a versioned contract
- tenant, user and role checks inside the harness (the identity is supplied by the caller)
- a versioned Need Record table with history
- a document store
- schema validation, side-effect classes and audit on tools
- a durable staged orchestrator with approval gates
- per-flow playbooks instead of the global SOUL.md
- per-task model routing with fallback
- prompt-injection isolation for all untrusted text

**Clean up:**
- stale `update_nit_draft` / `nit_flows` references
- the dead `_EXTRACT_FIELDS`
- `test_aan_extraction.py`
- the `/api/nit/*` endpoints in the UI config
- the out-of-date upload section in `docs/nrl-kg-integration.md`
