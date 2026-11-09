# NAM gap analysis (Step 3)

This maps every item in [frs-inventory.md](frs-inventory.md) (Step 1) to the harness as the [codebase audit](codebase-audit.md) (Step 2) found it.

**Scope.** The target is a strong Waku harness for the NAM domain. Testing runs on Waku itself.

**Data source principle**
- **Current:** Waku -> stable tool / data contract -> KG. The NRL KG already holds the SAP/Aarohan-derived history NAM uses today, so connectors are not a current dependency and no SAP/Aarohan stubs are added.
- **Future:** the same contract -> live SAP/Aarohan connectors, replacing or joining the KG without any flow changing (section 9).

**Status values**
- **have**: works and is tested.
- **partial**: some of it exists.
- **missing**: nothing exists.
- **blocked**: needs a definition or data from you (section 8).
- **future**: needs a live SAP/Aarohan connector, so it is not part of current work.

**What "Needed" refers to**
- **Harness parts:**
  - *playbook*: one flow per FRS function
  - *gate*: a stage check enforced in code
  - *tool*: schema-checked
  - *contract*: a data tool whose schema does not depend on its source; the KG serves it now
  - *engine*: deterministic code with no model call
  - *doc*: the document store
  - *eval*: an offline deterministic test
- **Build phases:** B foundation, C documents / knowledge / security, D flows, E trust and operations. These are the phases in `task.md`.

## What the KG holds

The KG's contents come from `/data2/nrl_dev/Harsh/KG/docs/kg-findings-and-plan.md`, and its endpoints (`/api/kg/tenders`, `precedent`, `prices`, `clauses`, `boilerplate`, `case`, `case_summary`, `documents`, `resolve`) are served on :8077.

**Present**

| Data | Size |
|---|---|
| Items | 5,553, 86% of them with a SAP `material_code` |
| Price records | about 37.9k |
| &nbsp;&nbsp;with an estimate rate | 37,253 |
| &nbsp;&nbsp;invoiced | 594 |
| &nbsp;&nbsp;award | 13 |
| &nbsp;&nbsp;bid | 3 |
| Price records with order qty / UoM | 98% |
| Contract / invoice / amendment dates | 97-99% |
| Suppliers | 504 |
| Bids | 1,506 |
| Awards | 184 |
| Specs | 1,001 |
| PQC | 416 |
| SCC | 439 |
| Documents, SOR references, departments | yes |

**Not held**
- Stock, consumption, open PRs
- Cost centre, budget head, WBS
- DoA thresholds and approval routing
- Live PR creation and the Aarohan file

These are listed in section 9 as future work, or come from the user in the flow.


## 1. Functions

| Id | Function | Status | What exists | Needed |
|---|---|---|---|---|
| F1 | Conversational entry | partial | Need capture from free text (`nam_capture.py`); reference lookup (`nam.lookup_reference`) | Entry point that takes messages + a short system prompt (B); playbook that routes the prompt to a flow (B) |
| F2 | Replicate from a reference | partial | `nam.replicate` from a KG tender; KG `/resolve` | Every reference type the KG can resolve goes through one `resolve_reference` contract; every autofilled field marked with its source (B, D) |
| F3 | Need capture and classification | partial | `NeedRecord` with classification, location, term, qty | Missing E2 fields: justification, purpose, required-by date, codes, UoM, route, supporting documents. A "mandatory need data complete" gate (B) |
| F4 | Predict fields, ask only what is not confident | partial | `classify` basis/confident; model-led follow-ups (`nam_followup.py`) | Follow-ups today narrow the tender list. R3 asks for questions per unconfident field; combine both in the capture playbook (D) |
| F5 | Unique File Number | partial | `NAM-YYYY-NNNN`, count-based | Atomic generation, unique per tenant (B) |
| F6 | Similar-case search | have | `similar_cases`, explained `match_strength` | The 70-80% threshold is undefined (section 8); "try another" loop state kept in the Need Record |
| F7 | Precedent selection by the user | have | `select` gate; generation reads `selected_cases` only | Check that the selected keys are in `related_cases`; audit entry recording who selected (B) |
| F8 | Guided form when nothing matches | missing | `flow_engine.py` (mandatory_if / na_if) can be reused | Four form definitions: Goods / Services / New Works / Repetitive Works (D) |
| F9 | Enterprise enrichment | partial | KG has material code, qty/UoM, estimate and invoiced rates, prior specs/PQC/SCC and suppliers, reached via `nam.py` and `kg_precedent.py` | An `enrichment` contract returning the E4 fields the KG holds. Fields it lacks (cost centre, budget head, WBS, PR type) are asked of the user as mandatory fields (D). The live SAP source is future work |
| F10 | Quantity finalisation | missing | KG `order_qty` / UoM on past lines (98%) | Playbook step: KG history as the suggestion, user approval gate (D). Stock and consumption are future work |
| F11 | Material / spec suggestion loop | partial | `selected_material` merges spec and BOQ from the selected tenders | "Satisfied?" loop adding search parameters; every user change recorded with a reason (D) |
| F12 | Edit / Review | partial | `apply_update`, classification fields only | Field-level edit of any Need Record field, versioned, with a reason (B) |
| F13 | Goods estimate | missing | `kg_price_reference`; KG price records with dates | Engine for R10/R11/R38 (VARN, CAGR, YRS, ALR/AHR) over a `price_history` contract that the KG serves (D). The KG holds only 607 invoiced or award prices, so last purchase price coverage is thin; the engine says when it has none |
| F14 | Wage estimate | missing | none | Engine for R12/R13/R39 (D). **blocked** on the wage rate list and reimbursable-items repository |
| F15 | Works estimate | missing | KG SOR references and estimate rates | Engine for the R5 hierarchy (Same / Similar / Derived) (C, D). **blocked** on the full rate books: NRL SOR, DSR, DAR |
| F16 | Basis of estimate | missing | none | Per-line source, rate class and match basis kept in the estimate record; no line without a source (D) |
| F17 | Document generation | missing | none | Doc generator (DOCX/XLSX) from templates; Generate -> Check -> Review -> Approve gates (C, D). **blocked** on NRL templates |
| F18 | SCC build | missing | `kg_clause_lookup`; KG SCC (439) and boilerplate | Pointwise merge per R16; "is SCC required?" step (D). Master clause repository needed for R18 |
| F19 | PQC build | missing | KG PQC (416) via `selected_material` | PQC / QCBS matrix builder (D) |
| F20 | Tech spec + compliances | missing | KG specs (1,001) via `selected_material` | Spec builder and compliance list (D) |
| F21 | BOQ build | partial | BOQ lines merged from the selected tenders | BOQ built from the finished estimate (R19); new items get vendor history from KG suppliers and awards (D) |
| F22 | Clause classification | missing | none | Standard vs contract-specific tagging, rule-based first (D) |
| F23 | Contract-specific fields | missing | `flow_engine` | Form per template (D) |
| F24 | AI review of drafts | missing | none | Model review whose output is checked against a schema; flags go to the drafter (D) |
| F25 | Document metadata, versioned | missing | none | Doc store with versions and the clause-selection summary (C) |
| F26 | Compliance checker | missing | none | Engine plus rules for MSE, OEM, technical and department (D) |
| F27-F29 | PR generation, one-click, PR number | missing | none | PR builder producing a schema-valid PR payload and a Procurix.ai PR file number; `submit_pr` contract marked as an irreversible action and held until confirmed (B, D). **blocked** on the bulk-PR Excel field list. The live SAP POST is future work |
| F30-F32 | Validation: format, completeness, consistency | missing | none | Deterministic checker across documents (qty, UoM, rate, dates) (D) |
| F33 | Checker against manual and circulars | missing | none | **blocked** on checklists, manual and circulars |
| F34 | Compare with references and previous versions | missing | KG documents of the selected tenders | Diff between document versions and against the reference (C) |
| F35 | Validation and freeze | missing | none | Freeze gate: all mandatory artifacts approved, version locked (B, D) |
| F36 | Package assembly | missing | none | Package builder per case type (D) |
| F37 | Aarohan approval routing | future | none | An `approval` contract shared with F45; the Aarohan side is a future connector |
| F38 | ANN | missing | `aan_reader` parses an AAN, but nothing calls it | ANN generation where no e-office exists (D) |
| F39 | Upload of documents edited outside NAM | missing | none | Doc upload, new version, corrigendum (C). Accuracy score **blocked** (definition) |
| F40, F50 | Push finalised documents to Aarohan | future | none | Package export through a `publish_package` contract (D); the Aarohan upload is a future connector |
| F41, F43, F44 | Handoff to NIT | missing | none (the UI's localStorage handoff is out of scope) | Structured handoff payload with a schema; gate R32; `handoff` contract returns the acknowledgement (D) |
| F42 | Feedback and audit on every change | missing | none | Audit entry with a reason on every edit (B, E) |
| F45 | Procurix.ai e-office approval | missing | none | Approval flow inside the harness, sign-off per DoA (D). **blocked** on the DoA thresholds (not in the KG) |
| F46 | Consolidated checker report | missing | none | One report that validates against a schema (D) |
| F47 | Empanelment check (Works) | missing | none | Engine: estimate is based on NRL SOR, substitutions flagged (D) |
| F48 | Text search for estimates | partial | KG lexical tender/item search, `/api/kg/prices`, material codes | A `price_history` contract (the same one as F13) served by the KG; estimate table; Excel export (C, D). The SRS SAP table path (MAKT, EBAN, EKPO, ESLL) becomes the future connector behind the same contract |
| F49 | Need-identification loop | partial | capture + follow-ups loop over KG tenders | Widen to the KG's other sources: bids, awards, invoiced prices, documents (D) |

**Count, out of the 50 functions:**
- 2 have
- 11 partial
- 34 missing
- 3 future (F37, F40, F50)

9 of the missing ones are partly blocked on definitions or data from you: F14, F15, F17, F27, F28, F29, F33, F39, F45. None are blocked on SAP/Aarohan.

## 2. Stages and gates

| Stage | Status | Source now | Gate today | Needed |
|---|---|---|---|---|
| S1 Need capture | partial | user + KG | none (stage label only) | Gate: mandatory need data complete |
| S2 Precedent enrichment | partial | KG | `select` (user picks) | Validate keys; record the approval in the audit log |
| S3 Qty finalisation | missing | user + KG history | none | Gate: user confirmation |
| S4 Estimate | missing | KG prices + rate books | none | Gate: estimate approved |
| S5 Documents | missing | KG precedent + templates | none | Gates: generate, check, review, approve |
| S6 Validation and freeze | missing | harness | none | Gate: all mandatory artifacts approved |
| S7 PR | missing | harness (PR payload) | none | Irreversible action, held until confirmed; live SAP POST is future work |
| S8 Approval | missing | harness (F45) | none | Gate: approval received; Aarohan routing is future work |
| S9 Upload | missing | user | none | Gate: new version recorded |
| S10 NIT handoff | missing | harness | none | Gate: NIT acknowledgement through the `handoff` contract; R32 |

**Needed across all stages:**
- A durable staged orchestrator: graph engine plus checkpoints stored in the Need Record.
- Code decides the next stage. No stage can be skipped.
- Two lifecycles write the stage field today (`capture` -> `references` and `matching` -> `selected`), and they must merge into one.

## 3. Roles

| Id | Role | Status | Needed |
|---|---|---|---|
| U1-U7 | Officer, User dept, Authorized user, Drafter, Functional reviewers, Commercial, Approvers | missing | Caller passes tenant, user and roles on each call; the harness checks them against a permission matrix per flow, gate and tool (B) |

The FRS has no permission matrix. I will draft one from section 3 of the inventory for you to confirm (**blocked** on your confirmation).

## 4. Business rules

| Rules | Status | Where / needed |
|---|---|---|
| R2 precedent chosen by the user | have | `nam.select`, `selected_material` |
| R3 ask only unconfident fields | partial | `classify.unresolved`; see F4 |
| R4, R34 similarity thresholds | partial | `match_strength` exists; thresholds undefined and not configurable |
| R28 category subtypes | partial | closed vocabularies in `nam.py`; Works New/Repetitive and Capital/Revenue to check |
| R1, R31 route decides the data | missing | route field on the Need Record; route picks the playbook (B) |
| R5-R9, R35-R37 rate hierarchy, latest rate, DSR alert | missing | Works engine + rate book contract (C, D); DSR alert as a guardrail (C) |
| R10, R11, R38 Goods VARN/CAGR | missing | Goods engine over the KG `price_history` contract (D); RC-then-PO ordering applied to KG price levels (award/invoiced before estimate) |
| R12, R13, R14, R39 Wage | missing | Wage engine (D); pure math, can be written before the data arrives |
| R15 Works input modes | missing | Works playbook; similar tenders and their documents from the KG (D) |
| R16-R18 clause rules | missing | SCC/PQC builder over KG clauses; "no mandatory clause omitted" check (C, D) |
| R19 BOQ from estimate | missing | ordering gate (D) |
| R20 mandatory before PR | missing | PR gate (B, D) |
| R21 compliance stages | missing | compliance engine (D) |
| R22, R23 validation, revalidate | missing | checker + re-run loop (D) |
| R24, R32 package gates | missing | freeze and handoff gates (B, D) |
| R25, R26, R40 re-upload, learning | missing | doc versions (C); training-data flag only, no learning loop yet |
| R27 reason on every change | missing | audit (B, E) |
| R29 QCBS matrix | missing | PQC builder (D) |
| R30 ANN only without e-office | missing | ANN playbook (D) |
| R33 scope ends at NIT | missing | routing refuses tasks outside NAM (B) |

## 5. Data entities

| Id | Entity | Status | Needed |
|---|---|---|---|
| E1 | Need Record | partial | Versioned table with history; one source of truth; the copies in the dossier file and localStorage become read views (B) |
| E2 | Requirement fields | partial | Add the missing fields (see F3) with a schema |
| E3 | PR | missing | Schema from the bulk-PR Excel (**blocked**) |
| E4 | Enterprise enrichment | partial | KG holds item, material code, qty/UoM, rates and prior documents; schema per SRS 2.2.3 with a source tag on each field |
| E5, E6 | Estimate line / estimate | missing | Schema with rate class, source and basis |
| E7 | Precedent | partial | `related_cases` / `selected_cases`; add who selected and when |
| E8, E13 | Document / uploaded document | missing | Doc store with versions and status |
| E9 | Clause | partial | KG SCC/PQC/boilerplate; clause schema plus the master repository for mandatory flags |
| E10 | Validation result | missing | Schema plus re-run history |
| E11 | Compliance requirement | missing | Schema |
| E12 | Package | missing | Schema plus freeze version |
| E14 | Audit entry | missing | Append-only audit table (B, E) |
| E15 | Reference data | partial | KG has past tenders, prices, BOQ, clauses, specs, SOR references. Full SOR/DSR/DAR rate books, the wage list, templates, the manual and the repositories are **blocked** |

## 6. Harness capabilities (task.md requirements and component table)

| Area | Today | Gap | Step |
|---|---|---|---|
| Entry point (messages + short prompt -> result) | `/api/chat` returns free text | Versioned request/response schema; replies checked against the schema | 5 |
| Identity, tenants, roles | none; one shared agent | Trusted identity context from the upstream auth component (no auth in Waku); role checks; per-tenant state; no shared consolidation | 6 |
| State (Need Record) | one JSON blob, upsert, 4 copies | Versioned, one source, history, atomic ids | 7 |
| Routing and playbooks | global SOUL.md, keyword skills | Deterministic prompt + stage -> flow; one playbook per function; out-of-scope refusal | 8 |
| Orchestration and human oversight | bare loop; graph engine has no checkpoints | Staged flow, gates, approval interrupts, irreversible actions held until confirmed | 9 |
| Tools | no input or output validation, no side-effect class | Schema checks, side-effect classes, retries, idempotency, audit per call, typed errors | 10 |
| Data contracts | KG called directly from `nam.py`, `nam_capture.py`, `kg_precedent.py` | One contract layer (`resolve_reference`, `enrichment`, `price_history`, `clauses`, `documents`, `approval`, `submit_pr`, `handoff`) with a source tag on every result; KG is the only backend today | 10, 13 |
| Documents | parsing only, never called | Upload, store, version, history, delete, OCR tool when no usable text (pluggable backend), generation; parsed text marked untrusted | 11 |
| Prompt-injection defense | one prompt line | Isolation wrapper for all untrusted text (documents, KG, web); pattern detection; output checks; size and type limits | 12 |
| Knowledge and retrieval | KG tools, honest about gaps | Citations and authority flags on every fact; rate books; clause repository | 13 |
| Guardrails | selection gate, no auto-open, recount of model questions | Duplicate PR/need, no invented rate (code check), DSR alert, threshold not final, category rules | 14 |
| Model routing | model + small_model; private `_call` | Model per task from config; fallback; public call; truncation handled | 16 |
| Audit and observability | traces without ids | Audit table (who, what, why, sources); request/tenant ids in traces; daily rollover | 17 |
| Evaluation | 87 NAM unit tests | Routing, schema, injection, gates, engines, end-to-end on Waku with the model and KG scripted | 18 |
| Loop robustness | ignores `max_tokens`, stream can duplicate | Handle stop reasons, iteration limit, error flag on tool results | 5, 10 |
| Cleanup | stale `update_nit_draft`, dead `_EXTRACT_FIELDS`, broken `test_aan_extraction.py`, outdated upload doc | Remove or rewire; fix the docs | 5 |

## 7. What can be built now vs what waits

- **Built now:**
  - all of Phase B
  - documents and injection defense (Phase C)
  - the KG-backed data contracts
  - the Goods engine on KG prices
  - the Wage and Works engines as pure math on test fixtures
  - quantity suggestion from KG history
  - the SCC/PQC/spec builders from KG precedent
  - the checker's format, completeness and consistency checks
  - package and handoff schemas
  - Procurix.ai approval flow logic
  - audit
  - evals
- **Waits for definitions or data from you:** the wage and rate book data, the PR field list, templates, the manual-based checker, DoA thresholds and the accuracy score. The engines take the data once it arrives.
- **Future work:** live SAP and Aarohan (section 9).

## 8. Inputs needed from you

1. The bulk-PR-upload Excel, which holds the PR fields, mandatory flags and code lists (F27-F29, E3).
2. A role / permission matrix and the DoA thresholds. I can draft both for you to correct (U1-U7, F45).
3. Rate data not in the KG: full NRL SOR, DSR/DAR, the wage rate list and the reimbursable-items repository (F14, F15).
4. NRL document templates for BOQ, SOR, SCC, PQC, spec, SOW and ANN, and the master clause and spec repositories (F17-F20, R18).
5. Checklists, the Procurement Manual and circulars (F33).
6. Definitions: the similarity metric for 70-80% and 95%, the accuracy score, and the tamper check (R4, R34, F39).
7. A decision on Emergency and consumption-pattern routes: the SRS drops them and the FRS has them (R31).

None of these blocks Phase B or C.

## 9. Future work: live SAP / Aarohan connectors

These plug in behind the same contracts. No flow, gate or schema changes when they do.

| Contract | Live source (future) | Adds what the KG does not hold |
|---|---|---|
| `enrichment` | SAP MM/PM/PS (EBAN, EKKO/EKPO, ESLH/ESLL) | cost centre, budget head, WBS, PR type, account assignment |
| `price_history` | SAP ME3M (RC), ME2M (PO); MAKT/EBAN/EKPO/ESLL text search | full last-purchase-price history |
| quantity inputs | SAP MM stock and consumption, PM calendars | stock, consumption, reorder levels, open PRs (duplicate-PR check against SAP) |
| `submit_pr` | SAP MM POST | live PR number and status (F28, F29) |
| `approval` | Aarohan workflow | Aarohan routing and decision, DoA from Aarohan (F37) |
| `publish_package` | Aarohan upload | file creation and document upload (F40, F50) |

Following the KG plan, SAP facts are stored as their own source tier (for example `sap_mm`) and do not overwrite document-derived values.
