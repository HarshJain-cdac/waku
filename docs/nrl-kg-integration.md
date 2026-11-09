# Connecting the NIT wizard to the tender knowledge graph

How waku-agent's NIT wizard reads NRL's tender knowledge graph, so a generated
NIT quotes real past tenders instead of approximating them.

- **waku-agent** — `/data2/nrl_dev/Harsh/waku-agent` (this repo)
- **KG** — `/data2/nrl_dev/Harsh/KG` (`nrl-slm-phase2`, the tender-precedent graph)

---

## The shape of it

```
waku-agent (.venv, py3.13)                KG (.abhi, py3.13)
                                    
  start_nit_flow      ─┐                  webapp/precedent_api.py
  advance_nit_flow     │  the user's        (read-only FastAPI, :8077)
    (nit_flows.py)     │  answers                    │
                       │                    /api/kg/precedent
  kg_item_history     ─┐                    /api/kg/items
  kg_tender_record     │                    /api/kg/resolve, /case, /documents
  kg_find_tenders      │                    /api/kg/tenders
  kg_precedent_search ─┼── HTTP ──────────▶ /api/kg/prices
  kg_price_reference   │  :8077             /api/kg/clauses
  kg_clause_lookup    ─┘                    /api/kg/boilerplate
        │                                            │
        ▼                                     NebulaGraph  nrl_kg
  nit_export.build_docx                       pgvector     nrl_vectors
        │                                     104,189 vertices
        ▼                                     318,578 embeddings
  .waku/nit/NIT_<session>.docx
```

Two processes, two virtualenvs, one HTTP contract. The KG pins llama-index,
nebula3-python and psycopg at exact versions; merging that into waku's lock
would couple two release cycles for no gain, and a separate process means the
KG restarting never takes waku down — the tools report themselves unavailable
and the wizard keeps working.

---

## The rule this integration is built around

**The user answers the questions. The KG does not answer them for them.**

The NIT is generated from what the user states, question by question, through
the existing wizard (`waku/tools/nit_flows.py` — a 37-question NIT flow and a
48-question AAN sub-flow, branching handled deterministically in
`flow_engine.py`). That did not change and was not bypassed.

The KG is **reference material**, in two places:

1. **During intake** — the agent may call `kg_precedent_search`,
   `kg_price_reference` or `kg_clause_lookup` to show the user what NRL did
   last time, so they can answer from precedent instead of memory. It may not
   submit a precedent value as their answer. The tool descriptions say this to
   the model explicitly, because that is where it will read it.
2. **At generation** — the PQC section, when the user supplied none, carries
   verbatim PQC clauses from the closest past tenders, each citing its source
   tender and labelled *for review*. They are suggestions attached to the
   document, not the document's PQC.

Nothing else is ever filled from the graph. A field the user did not answer
renders as `[TO BE FILLED: ...]`, in red, and is listed in the reply.

---

## Running it

Three tiers. Start them in this order.

```bash
# 1. KG precedent API  ->  :8077
cd /data2/nrl_dev/Harsh/KG
./scripts/start_precedent_api.sh --bg

# 2. waku backend      ->  :7777   (pinned in .env, and strict — see below)
cd /data2/nrl_dev/Harsh/waku-agent
.venv/bin/waku dashboard

# 3. nit-forge-ui      ->  :8082   (the UI the user actually works in)
cd /data2/nrl_dev/Harsh/waku-agent/nit-forge-ui
npm run dev
```

### Waku runs on 7777, and only 7777

| Port | Who |
|---|---|
| **7777** | this checkout's waku backend — `WAKU_DASHBOARD_PORT` in `.env` |
| **8077** | the KG precedent API |
| 8080 | the KG's own demo webapp |
| 8082 | the vite dev server (8080/8081 were taken) |

`waku dashboard` used to walk past a busy port to the next free one. It no
longer does **when the port is named**: an explicit `WAKU_DASHBOARD_PORT` (or
`PORT`) is treated as a requirement, and a busy port is a startup error:

```
port 7777 is not available ([Errno 98] Address already in use). ...
Waku will not start somewhere else — whatever points at 7777 would then be
talking to the wrong process. Free it (ss -ltnp | grep 7777) or set a
different port.
```

That is deliberate. `nit-forge-ui`, bookmarks and forwarded tunnels all address
7777; a backend that quietly started on 7778 is one nothing can find — and the
port it drifts to may belong to another checkout on this host. Another waku has
been seen on 7777 before (`/data2/nrl_dev/vinayak`); if it is running, it owns
the port and this one will refuse rather than compete.

An *unconfigured* run still walks, so a fresh clone does not crash on a busy
default. Both behaviours are pinned by `evals/deterministic/test_dashboard_port.py`.

`nit-forge-ui/.env` sets `VITE_API_BASE=http://localhost:7777`. Change one, change both.

### Reaching it from your own browser

The backend binds `127.0.0.1` by default, and the frontend calls it as
`localhost`, so "localhost" must mean this server. Two ways:

1. **Port forwarding (recommended).** VS Code Remote / `ssh -L` forwards 8082
   and 7777. Everything keeps working unchanged, and nothing is exposed.
2. **Straight over the LAN.** Then `localhost` is wrong — the backend has to
   listen on the network and the frontend has to name it:

   ```bash
   WAKU_DASHBOARD_HOST=0.0.0.0 .venv/bin/waku dashboard
   # and in nit-forge-ui/.env:
   VITE_API_BASE=http://10.180.148.183:7777
   ```

   `WAKU_DASHBOARD_HOST` defaults to `127.0.0.1` because this server has no
   authentication unless `WAKU_DASHBOARD_KEY` is set and it can read and write
   memory, calendar and NIT drafts. It prints a warning if you widen the bind
   without a key.

   This deployment runs without the key: the UIs do not send one, so with
   `WAKU_DASHBOARD_KEY` set every `/api/` call would answer 401. With
   `VITE_API_BASE=same-origin` the UI server on 8080 forwards `/api` to Waku,
   so only 8080 needs to be reachable.

---

## The AAN upload: what was broken

Uploading an AAN extracted nothing, so the wizard asked all 37 questions by
hand — including the ones in the file just uploaded. Four separate faults, each
sufficient on its own:

| Fault | Effect |
|---|---|
| `_extract_text` read `docx.paragraphs` only | An AAN is a **form**. On a real one that is the 62-character title; the 3,733 characters of tables — every field — were discarded. |
| The UI sends `doc_type: "aan_upload"` (the question key); the backend keyed on `"aan"` | `_EXTRACT_FIELDS` had no entry, so extraction returned `{}` **before the file was read**, and the upload question itself was never marked answered — so it re-asked for the file too. |
| `WAKU_SMALL_MODEL` unset | Fell back to the openai provider default `gpt-4.1-mini`, which this self-hosted vLLM does not serve. Every fallback extraction call 404'd, and `_extract_fields` swallowed it as `{}`. |
| `QuestionCard` never accepted or forwarded `onFileUploaded` | Even when the backend did extract, the result never reached the page, so the UI did not skip ahead. |

### How it works now

`waku/tools/aan_reader.py` reads the form directly: table rows are
label-and-value pairs, matched against `AAN_LABELS` with folded labels (so
`"Tender Type :"` and `"tender type"` are one row). **No model is involved** —
deterministic first, the LLM only for fields label-matching could not fill, and
a failed model call now degrades to "the fields we read off the form" instead
of to nothing.

Values are normalised to what the flow will accept: a form saying
`Open Tender` becomes `Open`, because a value the dropdown rejects is worse
than none — the user answers anyway *and* saw a suggestion get refused. A blank
row (`""`, `-`, `NA`) is left unanswered rather than recorded.

Measured on a real AAN (`PUR-INSTMNT-1000150`), over live HTTP:

- **29 fields** extracted, zero LLM calls
- AAN flow: **47 questions → 25**
- Starting the flow then uploading jumps from question 1 straight to
  **Cost Center** — the first field genuinely blank on that form

The `[nit]` extra carries `python-docx`, `openpyxl` and `pypdf`; the upload path
imported them optimistically before and would have failed at runtime without
them. Install with `uv pip install -e '.[nit]'`.

---

## Running the pieces



**1. Start the KG precedent API** (in the KG repo):

```bash
cd /data2/nrl_dev/Harsh/KG
./scripts/start_precedent_api.sh --bg     # or without --bg to watch it
```

It reports readiness with a health line: `{"ok":true,"space":"nrl_kg",
"tenders":151,...}`. Startup is tens of seconds — it imports llama-index and
opens a NebulaGraph session pool.

**2. Point waku at it.** Already set in `.env`:

```bash
WAKU_KG_URL=http://127.0.0.1:8077
WAKU_KG_TIMEOUT=120
```

**3. Run waku:**

```bash
cd /data2/nrl_dev/Harsh/waku-agent
.venv/bin/waku dashboard        # cockpit on :7777
.venv/bin/waku                  # or the terminal
```

Ask for a NIT (`generate a NIT`) and the wizard starts. At the end, **Generate
NIT** writes `.waku/nit/NIT_<session_id>.docx` and reports what is still blank.

**Unset `WAKU_KG_URL` and none of the `kg_*` tools register at all** — the
wizard behaves exactly as it did before. That is why the setting is a URL and
not an on/off flag: there is nothing to turn on without a service to point at.

---

## What each piece is

| File | Role |
|---|---|
| `KG/webapp/precedent_api.py` | Read-only FastAPI service. Every handler is a read; no statement in it is model-generated. Mirrors `src/nl_query.py`'s retrieval exactly — lexical + semantic lanes fused by RRF — so callers get the same precedent the KG's own drafter would use, and the same `precedent_gap` honesty check. |
| `KG/scripts/start_precedent_api.sh` | Launcher. Refuses to start a second copy on the same port. |
| `waku/nam/kg_tools.py` (was `waku/tools/kg_precedent.py`, which still imports) | The KG tools. Stdlib `urllib` only, no new waku dependency. |
| `waku/nam/nit.py` | The NIT template (ported row for row from `nit-forge-ui/src/lib/nit-template.ts`), filled from the case, empty rows suggested from the case's past tenders via `/api/kg/case` (blue, with the source tender), and a stdlib PDF writer. Gaps print `[TO BE FILLED]`; the estimate's rates never print. |
| `waku/ops/dashboard.py` | `GET /api/nit/<case>.json` is the filled sheet beside the chat; `GET /api/nit/<case>.pdf` the PDF, only once the NIT is ready (`?draft=1` any time, marked DRAFT); `?download=1` saves it; `POST /api/nit/<case>/field` accepts one suggestion. No longer reached from the chat: NIT generation is not part of NAM, so `generate_nit` is not registered. |

**One issued NIT is precedent, not authority.** It was a *Goods* tender on
*CPPP*; a Works or Services NIT, or a GeM tender, may legitimately differ. Every
generated document carries a provenance footer naming this source, so no reader
mistakes it for an approved blank. When the official template arrives, replace
`PROVENANCE` and the fixed rows in `waku/nam/nit.py` (and its mirror in
`nit-forge-ui/src/lib/nit-template.ts`) — nothing else needs to change.

---

## What the wizard does not collect

Eight rows of the NIT have no question behind them in `nit_flows.py`, so they
render as `[TO BE FILLED]` on every generated document:

| Row | Why |
|---|---|
| Tender No | assigned by the tendering system, not the drafter |
| Tender Publish Date | |
| Tender documents download start date & time | the whole **Tender Schedule** block — the flow has no date questions at all |
| Bid Submission start / end date & time | |
| Bid opening date & time (Technical Bid) | |
| Earnest Money Deposit (EMD) | reachable today only as a freeform edit ("change the EMD to 2 lakh") |
| Pre-Qualification Criteria (PQC) | the flow takes a PQC *file upload*; its text is not extracted into a field |

This is a gap in the intake spec, not in the export. Closing it means adding
questions to `nit_flows.py` — a change to the client's defined intake, so it is
deliberately not done here. Until then the export names every blank rather than
filling it, and PQC arrives as cited precedent for a human to adopt.

---

## Verifying it works

```bash
# KG side
curl -s http://127.0.0.1:8077/health
curl -s -G http://127.0.0.1:8077/api/kg/precedent \
  --data-urlencode "requirement=housekeeping chemicals" | head -c 400

# waku side — the tools register and reach the graph
cd /data2/nrl_dev/Harsh/waku-agent
.venv/bin/python -c "
import sqlite3
from waku.config import load_settings
from waku.tools import build_registry
s = load_settings()
r = build_registry(sqlite3.connect(':memory:'), s)
print(r.execute('kg_precedent_search', {'requirement':'housekeeping chemicals','limit':2}))
"

# the deterministic suite (baseline for this tree is 39 failed / 701 passed —
# those 39 pre-date this work; see the README note)
.venv/bin/python -m pytest evals/deterministic -q
```
