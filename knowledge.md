# Waku architecture: what each block does

This is the map of the Waku agent as it runs for NRL procurement: every block,
what it does, where its code is, and how a request passes through. The
dashboard's architecture diagram (`waku/ops/static/js/diagram.js`) draws the
same blocks; the table in "The diagram, block by block" at the end ties each
box to the code it stands for.

## The deployment

Everything runs on one server, 10.180.148.183.

| Port | Service | Reachable from | Code |
|---|---|---|---|
| 7777 | Waku backend and its built-in dashboard (chat, memory, ops) | the network, open (no key) | `waku/ops/dashboard.py` |
| 8080 | NAM frontend (nit-forge-ui); forwards `/api` to 7777 | the network | `nit-forge-ui/` |
| 3029 | Model server (vLLM, OpenAI-compatible, `gemma-4-31b-it`) | the network | not in this repo |
| 8081 | KG web UI (graph explorer and questions) | the network, open, when started with `KG/scripts/start_kg_network.sh` | `KG/webapp/server.py` |
| 8077 | KG precedent API (read-only) | the network, open, when started with `KG/scripts/start_kg_network.sh` | `KG/webapp/precedent_api.py` |
| 9669 | NebulaGraph (the tender graph), plus pgvector for embeddings | this server only | `KG/src/` |

Waku is opened to the network by `WAKU_DASHBOARD_HOST=0.0.0.0` (listen on all
interfaces). It runs without an access key, so anyone who can reach the
address can chat with the agent and read or change its memory, settings and
drafts; the server prints a warning about that at start-up. Waku's optional
`WAKU_DASHBOARD_KEY` (a bearer token on every `/api/` call) stays off, and
the UIs have no way to send one. User identity and roles for NAM come from
the platform's own auth component, never from Waku (D4).

## The picture

```
 browser (any machine on the network)
   |  dashboard :7777            NAM UI :8080 --proxy /api-->  :7777
   v                                   |
 +------------------------------- Waku backend (waku/ops/dashboard.py) ------------------------------+
 |                                                                                                   |
 |  CHAT TURN (waku/app.py respond)                         NAM HARNESS (waku/nam, POST /api/nam/run) |
 |                                                                                                   |
 |  Gateway --> Intent --> Working memory --> LOOP ------> Reply          request (system, messages) |
 |  web, cli,   rules,     SOUL + clock +     LLM agent      |   |          |                        |
 |  voice,      no model   gated memory +     <--> Tools     |   |        router -> permissions ->    |
 |  telegram..             matching skills      |            |   |        stage gate (S1..S10) ->    |
 |       ^                    ^                 |            |   |        guardrails -> playbook ->  |
 |       +---- reply, out the same gateway -----|------------+   |        guardrails -> verify ->    |
 |                            |                 |                |        audit -> nam.v1 reply      |
 |  Retrieval gate -----------+                 |                |          |                        |
 |    reads: Procedural (4 skills)              |                |          |                        |
 |           Semantic (facts, FTS5)             |                |          |                        |
 |           Episodic (past episodes)           |                v          |                        |
 |  Consolidation <-- saved chats               |              Trace -> Eval -> Release gate (Ops)   |
 +----------------------------------------------|---------------------------|------------------------+
                                                | HTTP                      | HTTP
                              Model server <----+ (both the loop and        |
                              vLLM :3029           NAM's model steps)       |
                                                                            v
                              KG precedent API :8077 <-- kg_* tools and NAM contracts
                                  |
                              NebulaGraph :9669 + pgvector
```

## The blocks

### 1. Front doors (gateways)

How a message gets in, and how the reply gets out the same way.

- **Built-in dashboard** at `:7777` (`waku/ops/static/`): chat, the
  architecture diagram, memory, tools, ops. Plain HTML and JS, no build step.
- **NAM frontend** at `:8080` (`nit-forge-ui/`, React), left as it is for
  now: its Procurix screens call `/api/nam/*` routes the backend no longer
  has (they followed the Procurix UI document, which is not the flow); its
  chat works, through `/api/chat`.
- **The PR Creation Flow** (the manual "PR Creation Flow in NAM"): the chat
  is the way in. The agent works its three stages with its own tools; see
  section 8 and [docs/nam/integration.md](docs/nam/integration.md).
- **CLI, voice, Telegram, Discord, WhatsApp** (`waku/gateway/`): the same
  turn, other doors. The dashboard process starts the chat gateways that are
  configured.

The backend is a standard-library HTTP server (`ThreadingHTTPServer`). Its
main routes: `/api/chat` and `/api/chat/stream` (a chat turn), `/api/events`
(the live trace the diagram animates from), `/api/data` (everything the
dashboard shows), `/api/nam/case/<id>` (a NAM case, its estimate and PR sheets),
`/api/settings`, `/api/memory`, `/api/models`.

### 2. Intent

`waku/tools/intent.py`. Reads the message with rules and labels the turn:
`greeting`, `nit`, `kg` or `task`. It costs no model call, because one call
to the shared model server can wait 2-20 s in its queue. Only a greeting is
answered here, instantly; every other label just tells the trace and the
diagram what the turn is about, and the turn continues unchanged.

### 3. Working memory

`waku/runtime/session.py` `build_system`. Builds the system prompt for this
turn:

- the persona (`.waku/SOUL.md`, or the built-in `DEFAULT_SOUL`), with the
  rules for NRL answers: cite the PUR case id, name the price level, never
  state a fact a tool did not give, "have we bought X" goes to
  `kg_item_history`;
- the current time and the model name;
- memories, only if the retrieval gate says they are needed;
- the skill text that matches the message.

Only the last `history_turns` exchanges go into the prompt, so a long
conversation does not get slower. Older turns come back through memory.

In a chat where NAM is set up, the prompt also carries the PR Creation
Flow's steps and the chat's own case (`waku/nam/flow.py`, read fresh from
`state.db` every turn): its need, the materials and the ones chosen, the
cart, each item's records still in, the answers and details given, the open
question and its options, the matching PURs and each item's PR. That is the chat's memory of the need: "them" and "that one" mean the
case's records, a side question is answered and the open question asked
again, and a restart loses nothing.

Two sources, two kinds of tool. SAP's records come from the KG MCP server
(`WAKU_KG_URL=http://10.180.148.183:8091/mcp`, `sap_search`, read through
`waku/nam/kg_mcp.py`): the numbers, the materials, rates, PR and PO numbers.
The tender knowledge graph (section 7, `WAKU_KG_API_URL`, the `kg_*` tools)
gives a PUR case's own data that SAP's lines do not show. `WAKU_KG_TOOLS=sap_search`
gives the agent SAP alone; `WAKU_KG_TOOLS=sap_search,nam` adds the PR Creation
Flow's tools.

The chat answers only NRL procurement work (`waku/nam/domain.py`,
`WAKU_DOMAIN_ONLY`, on where the KG is set): the agent decides, a word it
does not know is looked up in the KG first, and after a turn with no tool
the small model's `domain` task checks the reply; a strayed reply is written
again by the agent.

### 4. Memory (three pillars, a gate and consolidation)

`waku/memory/`.

- **Retrieval gate** (`retrieval_gate.py`): a small model call that decides
  whether this message needs memory at all, and with what query. Fails open:
  if it errors, the turn goes on without memory.
- **Semantic** (`semantic/`): durable facts in SQLite FTS5. Correcting a
  fact keeps its earlier version in `fact_history`, with when it was true;
  forgetting a fact deletes both.
- **Episodic** (`episodic/`): summaries of past conversations.
- **Procedural** (`procedural/loader.py`): skills, the `SKILL.md` files.
  Waku ships two:

  | Skill | Holds | Folder |
  |---|---|---|
  | `autonomous-work` | plan and verify each step, cite every figure, recover from tool failures, report | `skills/` |
  | `waku-memory` | connecting the hosted Waku Memory and exporting skills | `skills/` |

  A skill loads when the message shares two words with its name and
  description; a skill split into topics loads only the topics the message
  names. Skills
  a user teaches Waku are saved in `.waku/skills/`.
- **Consolidation** (`consolidation.py`): every few exchanges, saved chats
  are distilled into facts. A fact is kept only when its words are the
  user's own (never a tool's output), and it is compared with similar stored
  facts first: a repeat is skipped and a changed fact replaces the old one.
  [docs/memory-design.md](docs/memory-design.md) explains why.

### 5. The loop

`waku/loop/agent.py` `run_loop`: the model reasons, calls tools, reads their
results, and repeats until it can answer or reaches `max_iterations`. The
reply streams token by token to the gateway.

`waku/loop/models.py` is the client for the model server. Two fallbacks keep
the turn working on the current server:

- vLLM is started without `--enable-auto-tool-choice`, so it refuses requests
  that carry tools. The client then describes the tools in the system prompt
  and reads the calls back from the text (`WAKU_TOOL_MODE`).
- A model the server does not serve (the configured small model) falls back
  to the main model.

**The same answer whatever the model.** Every call is sampled at a fixed
temperature and seed (`WAKU_TEMPERATURE=0`, `WAKU_SEED=7`), so a question gets
the same answer each time. After each turn `waku/nam/answer_data.py` checks the
reply against what the KG tools returned: every tender found, each tender's
lowest bid per unit, the tender list, the matched price rows. What the reply
left out is added under "Data from the KG", as the graph returned it, so a
terse model and a wordy one carry the same data. `scripts/llm_consistency.py`
runs a fixed set of questions against the current model and compares two runs.

### 6. Tools

`waku/tools/` and `waku/nam/kg_tools.py`, registered in
`waku/tools/__init__.py`. What the model can call:

| Tools | What for |
|---|---|
| `kg_item_history` | "Have we bought X before?" and "compare them": every line item naming X (NRL abbreviations understood both ways, so "bimet" finds "Bimetallic" too), grouped per tender with rates and L1, plus a side-by-side comparison (specs, quantity, lowest bid per unit, bid spread, bidders) and how to answer a comparison; `tender=<PUR id>` reads one tender in full |
| `kg_find_tenders` | every past tender involving X (a complete list) |
| `kg_precedent_search` | the closest past tenders, for drafting; a weak result carries an item check |
| `kg_price_reference` | historical rates, one row per item, unit and price level |
| `kg_clause_lookup` | verbatim PQC, SCC and specification clauses with their tender |
| `kg_tender_record`, `sap_search` | a tender's PR, PO and files; SAP's PR, PO and service lines |
| `nam_need`, `nam_choose`, `nam_search`, `nam_ask`, `nam_answer`, `nam_pick`, `nam_undo`, `nam_tenders`, `nam_estimate`, `nam_pr`, `nam_case` | the PR Creation Flow, one tool per step, each gate checked in code (`waku/nam/stage_tools.py`, section 8) |
| `ask_options` | ask the user to pick from choices |
| `create_event`, `list_events`, `save_note`, `send_message`, `search_web` | calendar, notes, messages, web search |
| memory tools (`waku/tools/memory_admin.py`) | remember, forget, create a skill |

A KG tool that cannot reach the KG says "KG PRECEDENT UNAVAILABLE", never
"nothing found", so an outage is never reported as "NRL never bought it".

### 7. Knowledge graph service

A separate repo (`/data2/nrl_dev/Harsh/KG`) and process, reached over HTTP at
`WAKU_KG_API_URL` (`http://127.0.0.1:8077`), started with
`cd /data2/nrl_dev/Harsh/KG && ./scripts/start_kg_network.sh`. It is
read-only: no endpoint can write to the graph. The `kg_*` tools read it;
SAP's records are a separate source (`WAKU_KG_URL`, section 3).

- **Store**: NebulaGraph space `nrl_kg` (tenders, items, price records,
  bidders, PQC, SCC and specification clauses, documents) and pgvector
  (embeddings of items).
- **Endpoints**: `/api/kg/items` (item-level "have we bought X"), `/tenders`,
  `/precedent`, `/prices`, `/clauses`, `/boilerplate`, `/case`,
  `/case_summary`, `/documents`, `/resolve`, `/health`.
- **Matching**: lexical (full text) and semantic (embeddings) lanes fused;
  `src/item_match.py` reads NRL's abbreviations (TG = temperature gauge,
  BiMet = bimetallic, U320 = a 320 mm stem; a 5-letter abbreviation matches
  either way), compares sizes as numbers, and reads specifications from item
  names for tender comparisons.

Start it with `KG/scripts/start_precedent_api.sh --bg` (this server only), or
share it and the KG web UI on the network with `KG/scripts/start_kg_network.sh`:
one command runs both in the foreground, Ctrl+C or either one exiting stops
both, and Waku reads `http://127.0.0.1:8077`. Neither has a login, so anyone on the network can read
the graph; the UI's ingestion start and stop work only from the server
itself. It reads the Nebula address from the KG's own configuration.

### 8. NAM harness

`waku/nam/`. NRL's PR Creation Flow for goods. Its main output is the need
understood: the materials a job description names, how many of each SAP
holds (by short text and long text), the ones the officer takes forward, and
for each of those, one at a time, the one material code, put in a cart. Then
the PUR cases ranked by how many of the materials each holds, and one PR per
cart item. The estimate is there when the officer asks. Beside it, the harness API (`waku.nam.run`, `waku nam-api` on /v1/nam/*,
the dashboard's /api/nam/* routes; docs/nam/harness-api.md) runs the
stage machine of flows and gates for the Procurix screens and any other
client; `WAKU_NAM_CHAT=driver` puts its earlier need-capture driver back in
the chat. The flow is soft: the agent decides each next step in the chat, and
the harness keeps the case and checks every gate in code.

- **The guide** (`flow.py`): the manual's steps and the chat's case, in the
  agent's prompt every turn, with the step now and the step next.
- **The case** (`case.py`): one per need, linked to the chat that opened it;
  every write a new version (`nam_flow_case`, `nam_flow_case_versions`); a case belongs
  to the tenant of the caller that opened it.
- **The tools** (`stage_tools.py`), one per step: `nam_need` (1a-1c: the
  need and its materials, each searched in SAP at once and counted),
  `nam_choose` (1d: which materials go forward), `nam_search` (one item
  again, other words), `nam_ask` (1f: a question whose options the records
  bear out, placed and counted by `narrow.py`, refused with the reason
  otherwise), `nam_answer` (1f-1g), `nam_pick` (1h: one material from the
  records still in, into the cart; then the next item), `nam_undo` (the
  officer's acts taken back one at a time, never a confirmed PR),
  `nam_tenders` (1j: the PURs ranked by how many of the materials each holds,
  the most being 100%), `nam_estimate` (optional, `estimate.py`: last PO, 7%
  a year, YRS and CAGR, Cleared / AHR / Manual review / New item),
  `nam_pr` (stage 3, `pr.py`: one PR per cart item, no confirmation until
  every mandatory field is filled and a flagged price decided; SAP's PR
  interface is not connected, so a confirmed PR is "ready for SAP" with no PR
  number), `nam_case`.
- **Identity and permissions** (`identity.py`, `permissions.py`,
  `policy/permissions.json`): the trusted identity context another component
  sets (the X-NAM-* headers) is consumed, never authenticated here; each act
  needs a role the policy allows.
- **Around them**: `guard.py` (text from outside is data), `domain.py`,
  `answer_data.py` (the KG data a reply leaves out is added in code), `llm.py`
  (the one model task, `domain`), `audit.py` (one hash-chained row per tool
  call and model call), `kg_mcp.py` and `kg_tools.py` (the KG).

### 9. Model server

vLLM at `http://10.180.148.183:3029/v1`, OpenAI-compatible, serving
`gemma-4-31b-it`. Used by the loop, the retrieval gate and the NAM harness's
model steps. Not part of this repo; its start flags decide two speed and
behaviour points: `--enable-auto-tool-choice --tool-call-parser <parser>`
(native tool calls) and `--enable-prefix-caching` (reuse of the long, fixed
start of every prompt).

### 10. LLM Ops

`waku/ops/`. The offline loop that improves the agent:

- **Trace** (`tracing.py`): every turn's events (intent, gate, model calls,
  tools, KG lookups, reply) in `.waku/traces/`; the dashboard reads them live.
- **Eval**: `evals/deterministic/` (offline, 0/1; about 1,900 tests) and
  `evals/judge/` (model-graded).
- **Release gate** (`release_gate.py`, `make gate`): a prompt, model or
  config change ships only if the evals pass.

### 11. Optional triage graph

`waku/graph/`, off by default (`graph_workflows`). When on, a small graph
decides between a quick reply and the full loop before the turn; any failure
falls back to the plain loop.

## Two requests, end to end

**"Have we bought a bimetallic temperature gauge with a 320 mm stem?"** in
the chat:

1. The dashboard posts to `/api/chat/stream`.
2. Intent labels it `kg`; the diagram lights the KG block.
3. Working memory: persona, time; the gate skips memory; no skill matches.
4. The loop: the model calls `kg_item_history`.
5. The tool calls `/api/kg/items`; the KG reads all 12,480 line items and
   finds 8 exact rows ("TG Bimetallic U320mm ...", "TG BiMet ... U320T50")
   in PUR-INSTMNT-1003188 and PUR-INSTMNT-1002364, with L1 rates.
6. The model answers yes, citing both tenders; the turn is saved and traced.

**"Overhaul of line 4: replace gaskets, gate valves and thermowells"** in
the chat:

1. The agent opens the case with the three materials (`nam_need`); each is
   searched in SAP at once and counted: "valve: 3 materials, 3 by short
   text".
2. It asks which go forward (`nam_choose`); the options are the materials
   with their counts, and "All of them".
3. For each chosen item in turn, it asks what tells the records apart
   (`nam_ask`); the harness places each record under the option whose words
   it carries and shows the counts as buttons. Codes that share a short text
   are told apart by their long text. Each answer narrows the records
   (`nam_answer`) until one code is left; it goes in the cart (`nam_pick`),
   and the next item starts. "Undo" takes back any step (`nam_undo`).
4. The matching PURs (`nam_tenders`): the PUR holding the most of the three
   materials is 100%. Then one PR per cart item (`nam_pr`): the officer's
   fields, then the confirmation. The estimate only if asked.

## The diagram, block by block

What each box in the dashboard's architecture view stands for. The box ids
are the `data-node` values in `diagram.js`, which the live animation lights
from the trace.

| Box (`data-node`) | Stands for | Code |
|---|---|---|
| Gateway (`gateway`) | dashboard, NAM UI, CLI, voice, chat apps | `waku/ops/dashboard.py`, `waku/gateway/` |
| Intent (`intent`) | rules that label the turn, no model | `waku/tools/intent.py` |
| Working memory (`wm`) | the system prompt for this turn | `waku/runtime/session.py` |
| LLM agent (`llm`), Tools (`tools`) | the loop | `waku/loop/agent.py`, `waku/tools/` |
| Model server (`model`) | vLLM over HTTP | `waku/loop/models.py` (client) |
| Reply (`reply`) | the answer, out the same gateway | `waku/app.py` |
| Knowledge graph (`kg`) | the KG precedent API and its graph | `waku/nam/kg_tools.py`, `KG/webapp/precedent_api.py` |
| NAM harness (`nam`) | the PR Creation Flow: the agent's step tools, the case, the gates in code | `waku/nam/` |
| Retrieval gate (`gate`) | whether to read memory | `waku/memory/retrieval_gate.py` |
| Procedural, Semantic, Episodic | the three memory pillars | `waku/memory/` |
| Consolidation (`consolidation`) | chats distilled into facts | `waku/memory/consolidation.py` |
| Trace, Eval, Release gate, Release | LLM Ops | `waku/ops/`, `evals/` |

## Running it

```bash
# 1. the KG precedent API (once; it stays up)
cd /data2/nrl_dev/Harsh/KG && ./scripts/start_precedent_api.sh --bg

# 2. Waku, open to the network
cd /data2/nrl_dev/Harsh/waku-agent
WAKU_DASHBOARD_HOST=0.0.0.0 .venv/bin/waku dashboard

# 3. the NAM frontend, open to the network
cd nit-forge-ui && npm run dev -- --host 0.0.0.0
```

Then open `http://10.180.148.183:7777` (Waku) or `http://10.180.148.183:8080`
(NAM) from any machine on the network.
