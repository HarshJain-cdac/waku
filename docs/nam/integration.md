# NAM harness: the PR Creation Flow

NAM raises a Purchase Request (PR) for goods the way the manual "PR Creation
Flow in NAM" sets it out. The officer types a need in Waku's chat. The agent
works the manual's three stages with its own tools, and the harness keeps the
case and checks every gate in code. The chat is the way in: `POST /api/chat`
or `POST /api/chat/stream` on the dashboard server.

The harness API is the other way in, for the Procurix.ai backend and any
other client: `waku nam-api` (`/v1/nam/*`) and the dashboard's `/api/nam/*`
routes run the stage machine through `waku.nam.run()`. It has its own guide,
[harness-api.md](harness-api.md). Both ways read the same SAP records and the
same identity headers.

## 1. Run it

```
make dashboard          # the chat and the API on http://localhost:7777
```

Settings come from the environment:

| Variable | Default | What it sets |
|---|---|---|
| `WAKU_KG_URL` | none | the KG MCP server that serves SAP's records (`sap_search`), e.g. `http://10.180.148.183:8091/mcp`. NAM's flow counts and narrows these records. Without it NAM is off. |
| `WAKU_KG_API_URL` | `http://127.0.0.1:8077` | the tender knowledge graph's precedent API (`/data2/nrl_dev/Harsh/KG`, started with `./scripts/start_kg_network.sh`). The `kg_*` tools read it for a PUR case's data that SAP does not show. `mcp` reads the KG through `WAKU_KG_URL` instead. |
| `WAKU_KG_TOOLS` | every KG tool and the NAM tools | the KG tools the agent gets, comma separated. `sap_search` gives SAP's PR, PO and service lines alone; `sap_search,nam` adds the NAM tools, which then read SAP's records only. |
| `WAKU_DOMAIN_ONLY` | on where `WAKU_KG_URL` is set | the chat answers only NRL procurement work (`waku/nam/domain.py`). `0` turns it off, `1` turns it on anywhere. |
| `WAKU_NAM_MODELS` | the small model, then the main one | the models for the `domain` check, in the order tried: `domain=m1,m2`. |
| `WAKU_NAM_CHAT` | `flow` | what NAM is in the chat: `flow`, the PR Creation Flow below; `driver`, the earlier need-capture driver that runs in code (`waku/nam/drive.py`), for clients built on it |
| `WAKU_PROVIDER`, `WAKU_MODEL`, `WAKU_SMALL_MODEL` | the provider's defaults | the model provider and its two models |

## 2. The flow

The main output is the need understood. The officer types a need or a job
description; the agent takes out the materials it names, and SAP counts each
one. The officer chooses the items that go forward; each is narrowed, one at
a time, to one material code and put in a cart. Then the PUR cases are ranked
by how many of the materials each holds, and each cart item gets its own PR.
The estimate is there when the officer asks.

The agent reads the steps and the chat's case in its instructions every turn
(`waku/nam/flow.py`). It decides each next step itself; the steps are a
guide, not a script. Each step has one tool (`waku/nam/stage_tools.py`):

| Step | Tool | What the harness checks |
|---|---|---|
| 1a-1c category, need, materials | `nam_need` | the category is goods, services or works; each material is searched in SAP (`sap_search`) at once and counted: materials (a material code each), service lines, lines, and how they were found (by short text, by long text only, by meaning). An outage is never reported as "no record". |
| 1d choose the items | `nam_choose` | the options are the materials with their SAP counts, and "All of them"; the choice (names, numbers, or all) sets the order the items are worked in. No question about an item comes before the choice. |
| 1e-1f follow-up questions | `nam_ask` | each option carries words its records carry; the harness places every record under the first option whose words it carries and shows the counts. It refuses an option no record carries, an option every record carries, a label number a record does not carry, and a question where fewer than two options get records; the records no option reaches go under "Something else". |
| 1f-1g answers and defaults | `nam_answer` | an answer narrows the records (an option, words, or a material code); an answer that fits nothing asks one clarifying question. A detail taken from NRL's standard value is marked default and needs its source. |
| 1h into the cart | `nam_pick` | only a record still in after the answers, and only once three or fewer are left; then the next chosen item. `remove=true` takes an item out. |
| undo | `nam_undo` | the officer's acts (an answer, a detail, the choice, a material in the cart, a PR field) are taken back one at a time, by the case's versions; each undo goes one further back. A confirmed PR is never taken back. |
| 1j matching PURs | `nam_tenders` | the PUR cases ranked by how many of the need's materials each holds: the cart's picked codes, and every record of a material not taken forward. The PUR holding the most is 100%; one holding all of them is 100% only when it holds all. A PUR whose PR or PO SAP does not show is pointed to the knowledge graph (`kg_tender_record`). With `item=`, one item's past tenders. |
| estimate (optional) | `nam_estimate` | the cart's last PO rates, plus 7% for every year to the evaluation date; YRS and CAGR give Cleared, AHR, Manual review or New item. The lock waits until every flagged line is accepted, and writes `estimate.xlsx`. |
| 3a-3b one PR per item | `nam_pr` | each cart item's PR: its price is the locked estimate's, or the last price brought up to today with its result; a flagged price needs the officer's accept or rate. Every mandatory field (delivery date, plant, storage location, justification) before the confirmation; the fields given for one item's PR are offered for the next, and said so. SAP's PR interface is not connected, so a confirmed PR is "ready for SAP", written to `pr.xlsx` (one row per confirmed PR), and has no PR number. |
| any | `nam_case` | the case as it stands, or another case resumed in this chat |

Every number beside an option is counted from SAP and says what it counts:
"0-200 °C (7 materials)", "HE cover (1 service line)", or both. SAP gives the
numbers; the knowledge graph gives a PUR case's own data that SAP's lines do
not show.

While several records are in, `nam_search` and `nam_answer` give the agent a
digest to choose its next question from, not a table to paste: the kinds of
record, the words and values that split them with how many records carry
each, and the records in short. Codes that share a short text are listed with the words of each one's
long text the others lack, so the next question asks about that. The records
appear as a table once three or fewer are left to pick from. A detail recorded with `field=` that some of the
records carry narrows them too; a count or a date never does.

A tool that refuses says why, and the agent puts it right and calls it again.
The item is not searched again while its question is open, and the agent
cannot answer its own question in the turn it asked it.
After three refusals in a row the tool tells the agent to stop and ask the
officer in plain words. While a case is open, the generic `ask_options` tool
shows nothing: every choice the officer sees comes from `nam_ask`. A reply
that leaves out the estimate, a PR or the PUR ranking gets that table
added under "From the case" (`waku/nam/answer_data.py`). When a turn asks
nothing, the harness asks the open question again with its options.
Every tool call is one row in the hash-chained audit log (`waku/nam/audit.py`).

## 3. The case

`waku/nam/case.py` keeps one case per need, linked to the chat that opened it.
Every write is a new version in `nam_flow_case_versions`; a write based on an old
version is refused. The case holds the need, each item's records and the ones
still in, the answers and details, the open question, the choice of items,
the cart, the matching PURs, each item's PR and the estimate. Each write
names its act, which is how `nam_undo` goes back over the officer's acts.
The agent reads it every turn, so the chat remembers where the need stands.

`GET /api/nam/case/<NAM-YYYY-NNNN>` returns the case as JSON, and
`GET /api/nam/case/<id>/estimate.xlsx` and `/pr.xlsx` return its sheets.

## 4. Identity and permissions

Another component authenticates the caller and sets three headers on each
request (D4). Waku consumes them and never authenticates anyone:

| Header | Example |
|---|---|
| `X-NAM-Tenant` | `nrl` |
| `X-NAM-User` | `u123` |
| `X-NAM-Roles` | `U1,U3` or `officer,authorized_user` |

A request without them is this machine's own officer (tenant `local`, role
U1). A partial or malformed set gets HTTP 401. A case belongs to the tenant
that opened it, and no other tenant can read or change it.
`waku/nam/policy/permissions.json` says which roles may do each act: `need`,
`estimate.build`, `estimate.lock`, `pr.fill`, `pr.confirm`, `case.read`. The
matrix is a draft for NRL to correct.
