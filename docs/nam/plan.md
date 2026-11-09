# NAM harness implementation plan (Step 4)

This plan builds on [frs-inventory.md](frs-inventory.md), [codebase-audit.md](codebase-audit.md) and [gap-analysis.md](gap-analysis.md).

**Target.** A strong Waku harness for the NAM domain, tested on Waku itself.
- The backend calls it like an LLM: messages plus a short system prompt, and it gets back a structured result that has been checked against a schema.
- The KG is the data source behind stable contracts. Live SAP and Aarohan connectors are future work.

This plan also acts as the **proposal** that `docs/context/conventions.md` section 2 requires for a new top-level package (`waku/nam/`). Approving it approves that package.

## 1. Design decisions (please confirm or change)

| # | Decision | Why |
|---|---|---|
| D1 | NAM becomes its own package, `waku/nam/`. The existing modules `nam.py`, `nam_capture.py`, `nam_followup.py`, `nam_dossier.py` and `kg_precedent.py` move into it, and the old paths re-export them so existing tests and the dashboard keep working. | One place for the domain. The core loop, memory and personal-assistant parts stay untouched. |
| D2 | A separate server process, `waku nam-api`, on its own port (default 7788, loopback unless configured otherwise). The dashboard's admin routes are never exposed through it. | Keeps the attack surface small. The dashboard stays a dev tool. |
| D3 | Standard library only: `ThreadingHTTPServer`, and a small in-house JSON-schema validator (type, required, enum, properties, items, additionalProperties, min/max, maxLength, pattern). | Hard rule 3: no new default dependency. A validator this small can be fully tested. |
| D4 | **Identity comes from outside Waku.** Another component handles authentication, user identity and role propagation. Waku does not implement or redesign them: no API keys, logins, user directory or rate limiting. Waku only reads the trusted identity context passed with each call (tenant, user, roles) and uses it to enforce NAM workflow permissions: which roles may run a flow, pass a gate or confirm an action, and which tenant's cases and documents they may touch. | Auth belongs to the component that already owns it. Waku keeps only the NAM-specific checks. |
| D5 | Orchestration is a state machine in code over stages S1-S10, and its state is stored in the Need Record. The model only works inside a step, with that step's allowed tools and output schema. The graph engine is not changed. | Steps cannot be skipped, the flow resumes across calls, and the engine needs no proposal. |
| D6 | **Irreversible actions never come from the model.** Submitting a PR, freezing a package, sending the handoff and approvals come back as `pending_action`. They run only when the caller sends `confirm: {action_id}` with a role allowed to confirm. | The strongest defense against prompt injection and drift. |
| D7 | Playbooks are Python definitions (`waku/nam/playbooks/*.py`: flow id, FRS refs, stage, roles, tools, input/output schema, gates) plus one Markdown instruction file per flow. They replace SOUL.md for NAM calls. | Deterministic and testable. Instructions are kept per flow. |
| D8 | **OCR is a tool, not a pipeline stage.** Parsing runs normal extraction first. Only when that gives no usable text (a scanned PDF, an image, or unreadable machine text) is the `ocr_document` tool called, and then processing continues. The OCR backend is pluggable behind one interface; no engine is hard-coded. The tool returns the text with page and region metadata where the backend provides it. With no backend configured, the document is stored and marked "no usable text". | OCR runs only when needed, and any engine can be used later without changing flows. Hard rule 3: an engine's dependency goes behind an extra. |
| D9 | Storage is SQLite in `WAKU_HOME` (new `nam_*` tables) plus files under `.waku/nam/files/<tenant>/<case>/`. Existing `nam_needs` rows are copied into the new tables. Nothing is deleted. | Hard rule 1. |
| D10 | **Every step is verified before its reply goes out** (`waku/nam/verify.py`, added 2026-10-03). What a flow claims is checked in code against the case as stored: its artifacts recorded, inside their schemas, cited, their documents stored intact, a needed input stated, and the flow's own definition of done. A failed check turns `ok` into `needs_input` with the reasons, and the reply carries `verification`. A model's answer is used only once its check accepts it; a refused one goes back with the reason, at most twice (`llm.checked`). The whole case is verified again before the freeze and the handoff (guardrail `verification`). | A step can never report done what it did not finish, and the caller sees what was checked every step. |
| D11 | **A query can be a whole job** (`case.plan`, added 2026-10-03). The harness turns it into a to-do list of the flows from the case's stage to the goal the query names, stored on the case, and completes it step by step: each step through the same path as its own call (`_execute`: role, stage gate, guardrails, verification), done only when the case shows it done, stopping at a question, an approval, another role's step or a refusal; "continue" resumes. The plan proposes no approval and decides nothing itself. | The backend can hand over "complete this procurement" in one call site, and still every step is gated, guarded and verified. |
| D12 | **Flowless words take a step only when they need one** (router rule `words`, `waku/nam/intent.py`, `case.ask`; added 2026-10-05). Under a generic system prompt the user's message is read in code: a question, a greeting or "approve it" is answered without a step and changes nothing; "go ahead" continues the to-do list or the stage's next step; a change in words goes to the step of the case's stage that takes it and is read as that step's edit (after the step builds its lines, when it had none); words that look like a change but cannot be read fail verification (`message_applied`) instead of passing silently. | One generic call site covers the whole module, and the user's words are never dropped without saying so. |
| D13 | **NAM's domain knowledge is skills** (`waku/nam/skills/<name>/SKILL.md`, `skillset.py`, `extract.py`; added 2026-10-05). One skill per document (PQC, SCC, technical specification, BOQ and SOR, approval note), one for the rules every extraction follows, and NRL's three procurement manuals condensed (goods, works, services; full text in `reference.md`, never loaded), in Waku's skill format plus `flows` and `terms`, grounded in the FRS (2.2.5, 2.2.8, 1.2). Each states what the document is, what to extract and how, and its checks. The extraction runs in code, as each skill specifies (`extract.py`); `case.ask` explains from them, `docs.review` checks with them (warnings), and the review model is given their checks. The Waku chat agent loads the same files (one copy), by keyword match on descriptions written in procurement words only, held by the trigger eval; each skill stays under a token budget (`test_skill_budget.py`: 700 domain, 250 general) because a matched skill is read in full every turn. | The knowledge is readable and reviewable by NRL's officers, versioned with the code, and the same text drives the answers, the checks and the extraction. |

## 2. API contract (v1)

Base path: `/v1/nam`.
- **Identity context (D4):** `X-NAM-Tenant`, `X-NAM-User`, `X-NAM-Roles` (comma-separated), plus `X-Request-Id`. The upstream component that authenticates the caller sets these, and Waku trusts them as given. Waku only checks that they are present and well formed. The tenant `local` is reserved for the dashboard, which owns the cases created before tenants existed. The server binds to loopback by default, so only that component can reach it.
- **Response bodies:** every one carries `"version": "nam.v1"`.

### 2.1 The LLM-like call

`POST /v1/nam/run`

Request:
```json
{
  "system": "Assess need for request #123",
  "messages": [{"role": "user", "content": "We need 20 gate valves ..."}],
  "case_id": "NAM-2026-0123",
  "case_version": 4,
  "documents": ["doc_ab12"],
  "answer": {"question_id": "q1", "value": "spiral wound"},
  "confirm": {"action_id": "act_9f", "decision": "approve"},
  "options": {"skip_questions": false}
}
```

Response:
```json
{
  "version": "nam.v1",
  "run_id": "run_...",
  "case_id": "NAM-2026-0123",
  "case_version": 5,
  "flow": "need.capture",
  "frs": ["F1", "F3", "F4"],
  "stage": "S1",
  "status": "ok | needs_input | needs_approval | refused | error",
  "result": {},
  "questions": [{"id": "q1", "text": "...", "options": [{"label": "...", "value": "..."}]}],
  "pending_action": {"id": "act_9f", "kind": "submit_pr", "summary": "...", "allowed_roles": ["U3"]},
  "citations": [{"source": "kg", "ref": "tender:...", "authority": "precedent"}],
  "warnings": [],
  "next": ["quantity.finalise"],
  "route": {"by": "intent", "why": "the prompt matches need.capture (score 4)"}
}
```

`confirm` confirms the case's `pending_action`: a gate (quantity, estimate, clauses, documents) or an irreversible action (freeze_package, submit_pr, approve, handoff_nit). It runs only for a role allowed to confirm it and only if the case is unchanged since it was proposed; `decision: "reject"` needs a `reason`. The PR confirmation is the `submit_pr` action itself, so there is no separate PR gate. `answer` answers an open question from the last response (`value` `""` skips it). `case_version` is the one the last response gave; if the case has changed since, the call gets 409 `stale_version` and changes nothing. `result` has one schema per flow, stored under `waku/nam/schemas/`. Every response is validated before it is sent; a response that fails validation becomes `status: error` with code `internal_schema`.

### 2.2 Cases and documents

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/nam/cases/{id}` | current Need Record |
| GET | `/v1/nam/cases/{id}/history` | record versions |
| GET | `/v1/nam/cases/{id}/audit` | audit entries |
| POST | `/v1/nam/cases/{id}/documents` | upload (raw body; `Content-Type`, `X-Filename`, `X-Doc-Kind`) |
| GET | `/v1/nam/cases/{id}/documents` | list |
| GET | `/v1/nam/documents/{doc}` | metadata + parsed text (marked untrusted) |
| GET | `/v1/nam/documents/{doc}/content?version=n` | original file |
| GET | `/v1/nam/documents/{doc}/versions` | version history |
| PUT | `/v1/nam/documents/{doc}` | new version (edited outside NAM, F39) |
| DELETE | `/v1/nam/documents/{doc}` | soft delete: kept for audit, hidden from flows |
| GET | `/v1/nam/cases/{id}/trace` | the case traced to its inputs and approvals; `?format=jsonl` to export (Step 17) |
| GET | `/v1/nam/runs/{run_id}` | one call's audit rows, the caller's tenant only (Step 17) |
| GET | `/v1/nam/health` | liveness, KG reachability, the model per task |
| GET | `/v1/nam/schema` | all request and response schemas |

### 2.3 Errors

Errors use real HTTP status codes with this body:

```json
{"version": "nam.v1", "error": {"code": "...", "message": "...", "retryable": false}}
```

| HTTP status | Codes |
|---|---|
| 400 | `bad_request`, `schema` |
| 401 | `identity_missing` (identity context absent or malformed) |
| 403 | `forbidden_role`, `forbidden_tenant`, `forbidden_action` |
| 404 | `not_found` |
| 409 | `stage_gate`, `stale_version`, `in_progress` (a write with that idempotency key is still running; retryable) |
| 413 | `too_large` |
| 429 | `rate_limited` (more calls than `WAKU_NAM_RATE` a minute for one tenant and user; retryable) |
| 415 | `unsupported_type` |
| 422 | `guardrail` (a flow's output or an action broke a rule of `guardrails.py`; `details` names each rule and its FRS rule) |
| 501 | `flow_not_built` (routed and permitted, but the flow has no handler; every flow has one since Step 15) |
| 502 | `kg_unavailable`, `model_unavailable`, `ocr_unavailable` |
| 500 | `internal` |

Messages never contain stack traces or secrets.

## 3. Flows (playbooks) and FRS coverage

| Flow id | FRS | Stage | Roles |
|---|---|---|---|
| `need.capture` | F1, F3, F4, F5, F49 | S1 | U1 |
| `need.replicate` | F2 | S1 | U1 |
| `need.classify` | F4 (R1, R28) | S1 | U1 |
| `need.guided_form` | F8 | S1 | U1 |
| `precedent.search` / `precedent.select` | F6, F7 | S2 | U1 |
| `need.enrich` | F9 | S2 | U1, U3 |
| `quantity.finalise` | F10 | S3 | U1 |
| `material.suggest` | F11 | S3 | U1 |
| `case.edit` | F12, F42 | any, before freeze | U1, U3 |
| `estimate.goods` | F13, F16, F48 | S4 | U1, U6 |
| `estimate.wage` | F14, F16 | S4 | U1 |
| `estimate.works` | F15, F16, F47 | S4 | U1 |
| `docs.generate` | F17-F23, F25 | S5 | U1, U4 |
| `docs.review` | F24 | S5 | U4 |
| `compliance.build` | F26 | S5 | U2 |
| `validate` | F30-F34, F46 | S5-S6 | U3, U5 |
| `package.freeze` | F35, F36 | S6 | U5 |
| `pr.build` / `pr.submit` | F27, F28, F29 | S7 (`pr.submit` S7-S8) | U3 |
| `approval` | F37, F38, F45 | S8 | U7 |
| `document.update` | F39 | S9 | U1, U3 |
| `package.publish` | F40, F50 | S8-S10 | U6 (future connector) |
| `handoff.nit` | F41, F43, F44 | S10 | U6 |
| `case.status` | tracking | any | all |

**Routing (Step 8)** runs in this order:
1. **Parse the system prompt deterministically:** an intent table plus id extraction (`request #123`, `NAM-...`, tender/PR/PO refs).
2. **Resolve against the case's stage.** "Continue" means the next flow allowed at that stage.
3. **If still ambiguous,** one small-model call picks one of the flow ids (a closed list), and the answer is validated.
4. **Otherwise** return `needs_input`. Tasks outside NAM return `refused` (R33).

The exact order, with the answer, explicit-id, resume, category and last-message rules, is the docstring of `waku/nam/router.py`.

## 4. Package layout (file-level)

New `waku/nam/`:

| File | Content | Step |
|---|---|---|
| `__init__.py` | public `run(request) -> response` | 5 |
| `api.py` | `nam-api` HTTP server: routing, body limits, timeouts, errors | 5 |
| `schema.py` | JSON-schema subset validator | 5 |
| `schemas/*.json` | request, response, error, and each flow's `result`; Need Record; document; audit | 5, 7 |
| `client_example.py` | the one-file backend client (stdlib `urllib`), copied into the integration guide | 5, 19 |
| `identity.py` | reads the trusted identity context into `Caller(tenant, user, roles)`; no authentication | 6 |
| `permissions.py` + `policy/permissions.json` | enforces the role x flow x gate x action matrix and tenant scoping on cases and documents; the matrix is **drafted for your review** | 6 |
| `store.py` | tables (`nam_cases`, `nam_case_versions`, `nam_counters`), the import from `nam_needs`, optimistic versions, the atomic file number, and who wrote each version (the caller, set per call) | 7 |
| `record.py` | the Need Record and its history as `GET /v1/nam/cases/{id}` and `/history` show them (`schemas/record.json`, `history.json`). Pending actions join it in Step 9, and each flow's own fields in Step 15 | 7 |
| `router.py` | prompt + stage -> flow, in the order its docstring gives | 8 |
| `playbooks/__init__.py`, `playbooks/catalog.py`, `playbooks/instructions/<flow>.md` | every flow of section 3 as data (FRS, stages, intents, tools, result schema, handler), plus one instruction file per flow with per-category sections; a handler module per flow (`need_capture.py`, `need_replicate.py`, `need_classify.py`, `need_guided_form.py`, `precedent.py`, `enrich.py`, `quantity.py`, `materials.py`, `case_edit.py`, `estimate.py`, `documents.py`, `review.py`, `compliance.py`, `checker.py`, `package.py`, `pr.py`, `approval.py`, `uploads.py`, `handoff.py`, `case_status.py`), `lines.py`, the officer's line edits shared by them, and `checks.py`, the clause checks docs.review and validate share | 8, 15 |
| `orchestrator.py` | the stage machine S1-S10: per stage its checks (the flows' artifacts), gates (human approvals) and irreversible action; admission (409 `stage_gate`), rework back to an earlier stage before the freeze, the one pending action, `confirm` (approve or reject with a reason; stale if the case changed; claimed first so it runs once; effects stored per action id in `nam_action_results`) | 9 |
| `tools.py` | `NamTool` (side effect, roles, input/output schema, timeout, retries for reads, idempotency for writes in `nam_tool_results`), the audited `call()`, and an adapter to the core `Tool` for model use (read tools only) | 10 |
| `contracts/` | `base.py` (contract interfaces) and `kg.py` (the KG backend): `tenders`, `resolve_reference`, `enrichment`, `price_history`, `quantity_history`, `clauses`, `documents`, `suppliers`, `tender_record` (one tender's exact record, for create by copy). Every result carries `found`, `source`, `authority` and `warnings` | 10, 13 |
| `docs/store.py`, `docs/parse.py` | documents: store (bytes per tenant by SHA-256, checked on read), version, soft delete, upload idempotency; normal extraction for PDF/DOCX/XLSX (reuses `aan_reader`); a "usable text" check per page; type sniffing by magic bytes; size, page and zip-bomb limits; `documents` permissions | 11 |
| `ocr/base.py`, `ocr/__init__.py` | `OcrBackend` interface (`recognise(data, mime, pages) -> OcrResult`: text per page, regions with box and confidence where available, engine name) and a loader that picks the backend named in `WAKU_NAM_OCR_BACKEND` (`module:Class`); none by default | 11 |
| `ocr/tool.py` (`ocr_document` in the tool registry) | the OCR tool: read-only, called by `docs/parse.py` only for pages without usable text; reads only the acting tenant's files; output marked untrusted like any document text | 11 |
| `docs/render.py` | DOCX output for generated documents, standard library only (no extra): headings, paragraphs, tables; the same bytes for the same content, read back by `docs/parse.py` and stored by `docs/store.py` | 15 |
| `guard.py` | untrusted wrapper (`<untrusted source= id=>`, text normalised, hidden characters removed, block tags neutralised, instruction-like spans and secrets removed), instruction-pattern detector, output checks (no canary, secret, link, tool or action name, or id outside the allowed set), size caps, and a leak check on every reply (the prompt canary and the server's own secrets) | 12 |
| `guardrails.py` | duplicate need/PR, no rate without source, DSR alert, thresholds never final, precedent only if selected, category rules, R32 hand-off gate | 14 |
| `playbooks/estimate.py` | the three estimate engines: Goods (R10, R11, R38), wage (R12, R13, R39), Works (R5, R15, R34-R37, F47); their rules are checked again by `guardrails.py` | 15 |
| `playbooks/documents.py` | the document builders: estimate, BOQ, SOR, SCC, PQC, specification, scope of work (R16-R19, R29) | 15 |
| `playbooks/checker.py` | validate: format, completeness, consistency, integrity, versions, one report (F30-F34, F46) | 15 |
| `trace.py` | a case traced to its inputs and approvals, and one call's audit rows (`/trace`, `/runs`) | 17 |
| `llm.py` | the tasks that ask a model (`route`, `followup`), their models from `WAKU_NAM_MODELS` with fallbacks in order, a time limit per attempt, one shorter retry for a reply cut off at `max_tokens` (never used as it is), one audit row per attempt; each caller keeps its own check of the answer (router: a closed list; followup: recounted against the tenders) | 16 |
| `audit.py` | append-only `nam_events` (triggers refuse update and delete), hash-chained (`verify()` names the first changed or missing row, F33): one row per call, tool call, raw KG fetch, model attempt and document operation | 10, 17 |

Changes to existing files:

| File | Change | Step |
|---|---|---|
| `waku/tools/nam*.py`, `kg_precedent.py` | move to `waku/nam/`, keep re-export shims | 5 |
| `waku/loop/models.py` | public `create(..., extra=)` for provider options such as `reasoning_effort`, and `stop_reason` `max_tokens` for a reply cut off at its limit; ends the use of `_call` / `_to_openai` in `nam_followup` | 16 |
| `waku/__main__.py` | command `nam-api` | 5 |
| `waku/config.py` | `WAKU_NAM_*` settings: port, host, limits, model per task (`WAKU_NAM_MODELS`), KG url, OCR backend and usable-text threshold | 5, 11, 16 |
| `waku/runtime/session.py` | remove the stale `update_nit_draft` instruction | 5 |
| `waku/ops/dashboard.py` | drop the dead `_EXTRACT_FIELDS`; `/api/nam/*` calls `waku.nam.run` so there is one code path; fix the ignored HTTP code | 5 |
| `evals/deterministic/test_aan_extraction.py` | rewrite against `waku.nam.docs.parse` | 11 |
| `pyproject.toml` | an extra for the first real OCR adapter, once you pick the engine (D8) | 11 |
| `Makefile` | `make nam-api`, `make nam-eval` | 5, 18 |
| `docs/nrl-kg-integration.md`, `docs/status.md`, `docs/README.md` | fix what the change makes false; index the new docs | each step |

## 5. Order of work and evals per step

Each step ends green (`pytest evals/deterministic`, ruff) and adds its own evals in `evals/deterministic/nam/`. These evals are offline, with the model and KG scripted. Recorded KG fixtures are captured once from the live KG.

| Step | Builds | Eval that proves it |
|---|---|---|
| 5 | entry point, validator, errors, `need.capture` wired through `run()`, cleanup | every response validates; a bad body gets 400 and not a dropped connection; oversized body gets 413; the error body has no traceback; the old `/api/nam/capture` gives the same result through `run()` |
| 6 | identity context, permissions | missing or malformed context 401; other tenant's case or document 403; role not allowed for a flow, gate or confirm 403; Waku never reads credentials |
| 7 | Need Record store + migration | two calls on one case see one record; stale version 409; history lists every change with who and why; migration copies `nam_needs` without loss |
| 8 | router + playbook registry | routing table: every flow id reached from at least 3 prompt phrasings; out-of-NAM prompts refused; ambiguous prompts get `needs_input`; the model is only asked with a closed list |
| 9 | orchestrator, gates, pending actions | each stage refused before its gate (409 `stage_gate`); an irreversible action runs only with a valid `confirm` from an allowed role; resume after a restart |
| 10 | `NamTool`, contracts over the KG | schema reject on bad input and bad output; read retried, write not; idempotent write replay; one audit entry per call; `kg_unavailable` is not the same as "no data" |
| 11 | documents, OCR tool | PDF/DOCX/XLSX/image round-trip: upload, parse, view, new version, history, soft delete; wrong magic bytes 415; size 413; other tenant 403; OCR (scripted fake backend) is called only for a scanned PDF, an image or garbled text, never for a text PDF; page and region metadata kept; no backend gives "no usable text", not a crash |
| 12 | guard | hostile-document set (instructions in text, fake tool calls, closing-tag escapes, id smuggling): no tool call or state change is caused by document text; flagged in `warnings` |
| 13 | citations, authority flags | built: `waku/nam/knowledge.py` (the sources with their authority, `facts`, `uncited`), the `citation` guardrail, the `boilerplate` contract (NRL's standing NIT text) used by `compliance.build`, authority flags in the trace, the sources in `/v1/nam/health`; `test_nam_knowledge.py`; metric `uncited` (0 over the three end-to-end cases) and an opt-in live recall@5 over `retrieval_labels.json` (`scripts/nam_retrieval_labels.py`); precedent never auto-selected and no rate without a source stay guardrails `precedent` and `rate_source` |
| 14 | guardrails | one test per guardrail that tries to break it (duplicate PR, invented rate, DSR fallback without alert, handoff before approval) |
| 15 | flows one by one, in section 3 order | per flow: happy path, missing input, gate refusal, schema of `result`; engines have worked examples from the FRS diagrams (VARN/CAGR, wage 13.13%, reimbursement rounding) |
| 16 | model per task, fallback | the configured model is used and logged per task; the fallback is used on outage; a truncated reply gets a repair or an error, never a silent partial |
| 17 | audit, trace ids | any `result` field traces to its sources, tools and approvals; the hash chain detects an edited row |
| 18 | eval suite report | `make nam-eval` (`scripts/nam_eval_report.py` over `evals/deterministic/nam/nam_metrics.py`) prints routing accuracy, injection resistance, cross-document consistency catch rate, clause omission, schema validity and end-to-end Goods, Services and Works cases, each held to its threshold by `test_nam_metrics.py` and run in CI. No judge evals: no flow drafts text with a model. Uncited facts, replies verified and steps falsely reported done (`verified`, `false_done`) are measured offline; retrieval recall only against a live KG named by `WAKU_NAM_EVAL_KG_URL` (Step 13) |
| 19 | `docs/nam/integration.md` | a fresh client built from the guide passes the end-to-end smoke test |

Order inside Phase D follows the case lifecycle:
1. S1-S3 flows
2. The three estimate flows (Goods first, since it runs fully on KG prices)
3. Documents
4. Validation
5. Freeze and PR
6. Approval
7. Handoff

## 6. Not in this plan

- The NAM product frontend and backend.
- Dashboard hardening beyond what `nam-api` shares with it.
- Live SAP and Aarohan connectors. These are future work behind the same contracts; see gap-analysis section 9.

## 7. Waiting on you (does not block Steps 5-14)

1. Answers to D1-D9. D4 and D8 are updated to your direction.
2. Which OCR engine gets the first real adapter (D8). Until then, the evals use a scripted fake backend.
3. Your corrections to the drafted `permissions.json` and DoA thresholds (arriving in Step 6).
4. The data and definitions in gap-analysis section 8, needed before the matching Step 15 flows.
