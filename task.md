# NAM harness task

## Context

- Harness repo: /data2/nrl_dev/Harsh/waku-agent
- Spec: /data2/nrl_dev/Harsh/waku-agent/Procurix.ai_NeedAssessmentModule_FRS.docx
  (Procurix.ai Need Assessment Module – Functional Requirements Specification)
- Detailed SRS: /data2/nrl_dev/Harsh/waku-agent/NAM_Detailed_SRS_Reorganized_v2.docx.pdf

## Goal

Turn waku-agent into a strong, plug-in agent harness for the Procurix.ai
Need Assessment Module (NAM). We are NOT building the NAM frontend or backend.
The backend only adds the Waku harness API. From then on, the harness must
handle every NAM task from start to finish.

## Integration model

- The Waku API is exposed through one client/config file on the backend.
- The backend can call it from many places, the same way it would call an LLM.
- Each call carries only a very small system prompt (e.g. "Assess need for
  request #123" or "Validate this requirement document"). The harness must
  work out the right NAM task from that alone. It does this with its own
  built-in NAM knowledge: FRS workflows, business rules, data schemas,
  approval stages and validations.

## Requirements (the harness must be strong in all of these)

1. Task understanding and routing: pick the correct NAM flow from a short
   prompt, using internal playbooks per FRS function, and follow the FRS
   exactly without drifting.
2. Tool calling: tools with clear schemas, strict input and output
   validation, retries, error handling, deterministic results, and audit logs.
3. Documents: upload, parse, view/retrieve and maintain (update, version,
   history, delete). Supported formats: PDF, DOCX, XLSX and images. Uploaded
   documents are treated as untrusted data.
4. Security: API auth, tenant and user isolation, role-based access following
   the FRS roles, input sanitization, prompt-injection defense (especially
   from uploaded documents), secrets handling, rate limiting, and audit trail.
5. Robustness: structured, schema-valid outputs, graceful failures, state or
   session handling across multiple calls, observability, and tests.
6. Clean API surface: one simple entry point that looks like an LLM call
   (messages + short system prompt → structured result), plus
   document endpoints.

## First step (read-only, do not change code yet)

1. Read the FRS docx fully and list every NAM function, workflow, role,
   rule, data entity, and output.
2. Read the current waku-agent codebase: architecture, agent loop, tools,
   API, security, and document handling.
3. Produce a gap analysis mapping each FRS function to what the harness has
   now, what is missing, and what is needed. Cover routing, tools, documents,
   security and API.
4. Propose an implementation plan with phases and file-level changes.
   Wait for my approval before building anything.

**Working preference:** give me the shell commands to run instead of running
them yourself; I will paste the output back.


## NAM architecture components vs Waku today

| Component | Role | What it means for NAM | Waku today |
|---|---|---|---|
| **Model** | The reasoning and language engine. | Which model handles which step, for example the SLM for non-technical drafting and an external LLM for technical content. | Provider config exists. No per-task routing. |
| **Instructions / policy** | Persona, rules, procedure. | NRL rules, the Goods / Works / Services separation, and "thresholds are never final". These should be per-agent, not one shared file. | One global `SOUL.md`. |
| **Tools / actions** | What the agent can do, with schemas and permissions. | SAP read and write, Aarohan fetch and route, estimator, clause lookup, document builder, validator. Each has a side-effect class (read, write, irreversible). | Registry and schemas only. |
| **Orchestration** | Control flow: the loop, plus who decides the next step. | A staged workflow with gates (need → estimate → documents → PR → validation → package). Code decides the path and the model works inside each step. | Bare loop. We hand-built the bypass for the wizard. |
| **State / working memory** | What this case knows right now. | The Need Record: one durable source of truth per requirement, separate from chat history. | Partial (`nit_drafts`), with the two-sources-of-truth bug. |
| **Knowledge / retrieval** | Grounding in approved material. | Clause library, SOR/DSR/DAR, past tenders, procurement manual, with citations and source-authority flags. | Weak. |
| **Long-term memory** | What persists across cases. | Precedent history and edited documents users re-upload, subject to data governance. | Generic facts and episodes, not shaped for this. |
| **Guardrails** | Limits enforced outside the model. | Never auto-select a precedent, never invent a rate, block a duplicate PR, treat uploaded documents as untrusted input, hold irreversible actions until confirmed. | Prompt requests only. |
| **Human oversight** | Approval and override points. | Review at quantity, estimate, clauses, documents and PR confirm, plus the Aarohan approval routing. | None. |
| **Identity and access** | Who is acting and what they may do. | Officer, drafter and approver roles, and SAP data scope. | None (`session_id` is only a label). |
| **Observability and audit** | Record of what happened and why. | Basis of estimate, why a rate was classed as "Similar", which clauses were chosen, who accepted what. | Debug traces only. |
| **Evaluation** | Measured reliability. | Retrieval quality, clause-omission rate, cross-document inconsistency catch rate, SAP acceptance of generated PRs. | None. |
| **Interfaces (inputs and outputs)** | How the agent perceives and delivers. | Chat, structured events to the frontend, document uploads, Excel and PDF ingestion, SAP and Aarohan payloads. | Chat and events exist. Ingestion is partial. |

# Work plan, step by step

We cover one step at a time. A step starts only after the previous one is approved. Each step lists what it produces and when it counts as done.

Legend: `- [ ]` not started · `- [ ] ... (in progress)` · `- [x]` done


## Phase A: understand (read-only, no code changes)

- [x] **Step 1. FRS + SRS inventory**
  - FRS: `Procurix.ai_NeedAssessmentModule_FRS.docx` · SRS: `NAM_Detailed_SRS_Reorganized_v2.docx.pdf`
  - Read the FRS docx in full. List every NAM function, workflow, role, business rule, validation, approval stage, data entity (with fields), and output (documents, PR, payloads).
  - **Output:** docs/nam/frs-inventory.md (SRS differences in its section 9), one numbered item per FRS clause so later steps can cite "FRS 2.1.3".
  - **Done when:** you confirm nothing in the FRS is missing from the list.
- [x] **Step 2. Codebase audit**
  - Read waku-agent as it is now: agent loop, tool registry, API (dashboard.py), memory, state (nam_needs, nit_drafts), documents, config, security (auth, CORS, keys), evals. Include what was built for NAM so far (nam.py, nam_capture.py, nam_followup.py, nam_dossier.py, KG tools).
  - Scope: a strong Waku harness for the NAM domain, tested on Waku itself; not a full product backend.
  - **Output:** docs/nam/codebase-audit.md, what exists, where, and how solid.
  - **Done when:** you agree it matches the code.
- [x] **Step 3. Gap analysis**
  - Map each FRS item from Step 1 to the harness: have / partial / missing / what is needed. Cover routing, tools, documents, security, API, state, guardrails, human oversight, audit, evaluation (the table above).
  - **Output:** docs/nam/gap-analysis.md.
  - **Done when:** you approve the gaps.
- [x] **Step 4. Implementation plan**
  - Phases, file-level changes, the API contract, the order of work, and the eval each phase adds. Refines Steps 5 to 18 below with FRS numbers.
  - **Output:** docs/nam/plan.md.
  - **Done when:** you approve it. Nothing is built before this.

## Phase B: the harness foundation

- [x] **Step 5. One entry point that looks like an LLM call**
  - POST /v1/nam: messages + a short system prompt ("Assess need for request #123") -> one structured, schema-valid JSON result. A single client/config file for the backend. Versioned request and response schemas.
  - **Done when:** the backend can call it like an LLM and every reply validates.
- [x] **Step 6. Identity context, tenants, roles**
  - Authentication, user identity and role propagation are handled by another component (plan D4). Waku reads the trusted tenant, user and roles on every call and enforces the FRS roles (officer, drafter, approver, ...) on each flow, gate, action and tool.
  - **Done when:** a call from the wrong role or tenant is refused, with a test.
- [x] **Step 7. The Need Record: one source of truth per case**
  - A durable, versioned case record separate from chat history, keyed by request id, carrying every field the FRS defines, its stage and history. Replaces the two-sources-of-truth problem (nit_drafts vs chat).
  - **Done when:** several calls on the same request id see and update one record.
- [x] **Step 8. Task routing and playbooks**
  - From the short system prompt plus the Need Record's stage, pick the FRS flow deterministically in code. One playbook per FRS function (steps, rules, allowed tools, required outputs), per-agent instructions instead of one SOUL.md (Goods / Works / Services separation).
  - **Done when:** a routing eval covers every FRS function with no drift.
- [x] **Step 9. Staged orchestration with gates and human approval**
  - need -> references -> estimate -> documents -> PR -> validation -> package, as code. The model works inside a step; code decides the next step. Approval points at quantity, estimate, clauses, documents, PR confirm. Irreversible actions held until confirmed.
  - **Done when:** no step can be skipped or reached without its gate passing.
- [x] **Step 10. Tool layer hardening**
  - Strict input and output schemas, side-effect class per tool (read / write / irreversible), retries with backoff, idempotency keys, deterministic results, clear errors, every call written to the audit log.
  - **Done when:** every tool has schema tests and a failure-path test.

## Phase C: documents, knowledge, security

- [x] **Step 11. Documents**
  - Upload, parse, view/retrieve, update, version, history, delete for PDF, DOCX, XLSX and images. OCR is a tool called only when normal extraction gives no usable text, with a pluggable backend (plan D8). Stored per tenant and case. Parsed content marked untrusted.
  - **Done when:** each format round-trips with version history, with tests.
- [x] **Step 12. Prompt-injection defense and input sanitization**
  - Uploaded and retrieved text is data, never instructions: isolation in prompts, instruction-pattern detection, output checks, size limits, file type checks, secrets never reachable by the model.
  - **Done when:** an injection eval set (hostile documents) passes.
- [ ] **Step 13. Knowledge and retrieval** *(built, waiting for your review)*
  - Past tenders (KG), clause library, SOR/DSR/DAR rates, procurement manual, each answer cited with source and an authority flag. Never auto-select a precedent, never invent a rate.
  - **Done when:** retrieval evals meet agreed recall and zero uncited facts.
  - Built: `waku/nam/knowledge.py` (sources with authority flags, `facts`, `uncited`), the `citation` guardrail, the KG `boilerplate` contract shown in `compliance.build`, authority in the trace and `/v1/nam/health`. Zero uncited facts is measured offline (metric `uncited`). Recall@5 runs only against a live KG (`WAKU_NAM_EVAL_KG_URL`) over `retrieval_labels.json`, which `scripts/nam_retrieval_labels.py` builds; on 2026-10-03 the KG's graph host was unreachable, so the set is still empty and the 0.9 threshold is a draft.
- [x] **Step 14. Guardrails enforced outside the model**
  - Block duplicate PRs, thresholds never final, no invented rates, no precedent without officer selection, category rules. Checked in code before and after each step.
  - **Done when:** each guardrail has a test that tries to break it.

## Phase D: the NAM flows themselves

- [ ] **Step 15. Implement each FRS function as a playbook flow**
  - One sub-step per FRS function from Step 1 (need capture, reference and replication, category, guided description, similar cases, estimate, document generation, PR creation, validation, package and handoff, tracking), each with its inputs, outputs, rules and evals. We take these one at a time.
  - **Done when:** every FRS function runs end to end through /v1/nam.
  - [x] 15.0 need capture (F1, F3, F4, F5, F49): built in Step 5
  - [x] 15.1 reference and replication (`need.replicate`, F2)
  - [x] 15.2 category (`need.classify`, F4, R1, R28): the S1 gate needs the category, procurement type and tender type confirmed; a confident prediction counts; the sub-type is optional
  - [x] 15.3 guided description (`need.guided_form`, F8): the four forms in `policy/guided_forms.json` (DRAFT); only a complete form captures the need; the fields stay DRAFT until checked against Diagram B
  - [x] 15.4 similar cases (`precedent.search` F6, `precedent.select` F7): only a tender shown and named can be selected; the officer's order is kept
  - [ ] 15.5 quantity and estimate (`quantity.finalise` F10; `estimate.goods`, `.wage`, `.works` F13-F16, F47): every rate cited, typed or a policy rule, else a New Item *(completed 2026-10-03 against the FRS, waiting for your review)*: the estimate gate needs every line priced and an estimate of the current quantity; ESI/WCI per line; manpower inside Works priced as wages (R14); F13 header (dates, cost centre, location); the scope of work on the quantity
  - [ ] 15.6 document generation (`docs.generate` F17-F25): verbatim precedent clauses, stored as versioned .docx *(built, waiting for your review)*
  - [ ] 15.7 PR creation (`pr.build` F27, `pr.submit` F28, F29): the PR field list is a draft *(completed 2026-10-03 against the FRS, waiting for your review)*: items carry rate and amount; cost centre from the estimate; the SRS's optional SAP fields added to the draft list; the SAP PR status recorded; one SAP PR number per case
  - [ ] 15.8 checking (`docs.review` F24, `compliance.build` F26, `validate` F30-F34, F46): conflicts found in code, a review model only about clauses it was shown; `policy/compliance.json` is a DRAFT *(built, waiting for your review)*
  - [ ] 15.9 package and approval (`package.freeze` F35, F36; `approval` F37, F38, F45): `policy/doa.json` is empty until NRL's DoA is given, so the approver names the authority *(built, waiting for your review)*
  - [ ] 15.10 upload and handoff (`package.publish` F40, F50; `document.update` F39; `handoff.nit` F41, F43, F44): no Aarohan or NIT connector, so uploads and the handoff are recorded *(built, waiting for your review)*
  - [ ] 15.11 the side flows (`need.enrich` F9, `material.suggest` F11, `case.edit` F12, F42) *(built, waiting for your review)*
- [ ] **Step 16. Model routing per task** *(built, waiting for your review)*
  - Which model does which step (small model for drafting and routing, larger model for technical content), set in config, with fallbacks.
  - **Done when:** each task's model is configurable and logged.
  - Built: `waku/nam/llm.py`, tasks `route` (small model) and `followup` (main model), `WAKU_NAM_MODELS` with fallbacks, one audit row per attempt, the models per task in `/v1/nam/health`.

- [ ] **Feedback loop: every step verified** *(built 2026-10-03, waiting for your review)*
  - `waku/nam/verify.py`: after each step, its claim is checked against the case as stored (artifacts recorded, in schema, cited, documents intact, input stated, the flow's own "done"); a failed check turns `ok` into `needs_input` with the reasons and offers the step again; every reply carries `verification` with what the stage still needs. Model answers are re-asked with the rejection reason up to twice (`llm.checked`, used by routing, follow-up questions and review). The whole case is verified again before freeze and handoff (guardrail `verification`). Evals: `test_nam_verify.py`; metrics `verified` (100%) and `false_done` (0). The frontend's Harness panel shows each step's verification.

- [ ] **To-do list and step-by-step completion** *(built 2026-10-03, waiting for your review)*
  - `case.plan` (`waku/nam/playbooks/plan.py`): the user's query becomes a to-do list on the case (goal read from the query, default the NIT handoff); each call runs the next items through the same path as their own calls (`waku/nam/__init__._execute`), marks an item done only when the case shows it done, and stops at a question, an approval, a step for another role or a refusal; "continue" resumes. The list follows reworks and adds the guided form when no precedent fits. Evals: `test_nam_plan.py` (a whole Goods case completed from one query); metric `planned`. The frontend has a To-do list panel.

- [ ] **Flowless work: words that name no step** *(built 2026-10-05, waiting for your review)*
  - Probed first: of 20 such requests only 5 were handled; a quantity or rate given in words ran the step and changed nothing. Now: `waku/nam/intent.py` reads the message (question, show, approve, proceed, greeting, a change in words), router rule `words` takes the step it needs, `case.ask` (read-only, cited, `policy/glossary.json` DRAFT) answers the rest, a change in words is applied as the step's edit, and unread change words fail verification (`message_applied`). Evals: `flowless_corpus.py` (60 requests) in `test_nam_flowless.py`; metric `flowless` 100%. The frontend's To-do panel has "Send my words".

- [ ] **NAM knowledge skills: PQC, SCC, what to extract and how** *(built 2026-10-05, waiting for your review)*
  - `waku/nam/skills/`: `nam-pqc`, `nam-scc`, `nam-tech-spec`, `nam-boq`, `nam-aan`, `nam-extraction`, each with what it is, what to extract, how, and its checks (FRS 2.2.5, 2.2.8, 1.2). `waku/nam/extract.py` extracts in code as they specify (PQC criteria with their thresholds and periods, SCC terms with figures and units, specification standards and ratings, BOQ table lines, approval-note fields), shown as `content.extracted` on documents of those kinds. `case.ask` explains from the skills; `docs.review` warns on PQC thresholds off `policy/pqc_norms.json` (DRAFT) or copied rupee figures, incomplete LD or performance security, and makes without "or equivalent"; the review model gets the skills' checks. The Waku chat agent loads the same skills (`waku.memory.bundled_skill_dirs`), each with an "In chat" section; the trigger eval holds them to their own messages and off everyday ones. Evals: `test_nam_skills.py`, `test_skill_triggers.py`.

- [ ] **Four skills, loaded by topic** *(built 2026-10-07, waiting for your review)*
  - Waku ships four skills: `autonomous-work` (plan, verify, cite, recover from tool failures, report; merges step-by-step, fact-check, tool-failure-recovery, final-report), `waku-memory` (trimmed), `nam-documents` (PQC, SCC, specification, BOQ, AAN and the extraction rules as topics) and `nrl-procurement` (goods, works, services topics; manual texts in `reference-*.md`). The chat loads only the topics a message names (`loader.Skill.focus`, `SkillLoader.load`), and a second matched skill only for a topic it names: a PQC question loads ~400 tokens. Harness topics are `<skill>/<topic>` (`skillset.py`). Evals: `test_skill_budget.py` (exactly four skills; shared 250, topic 550, per message 1,400 tokens), `test_skill_triggers.py` (each message's skill and topic), `test_nam_skills.py`.

- [ ] **Skills narrowed to the project and token-optimised** *(built 2026-10-06, superseded by the four skills above)*
  - Removed the personal-assistant skills (`schedule-meeting`, `weekly-brief`) and the old community examples. The NRL manual texts someone had written over the community folders (goods, works, services; unreadable: CRLF, folded descriptions, over 80 lines) are now `waku/nam/skills/nrl-procurement-*` (condensed, every figure kept, full text in `reference.md`). New general skills `step-by-step`, `fact-check`, `tool-failure-recovery`, `final-report` (130-190 tokens each); the same rules always-on in the default persona (`DEFAULT_SOUL`). NAM skills condensed from 700-1070 to 360-610 tokens; NRL ones from 1300-1700 to 560-675. `test_skill_budget.py` holds the budgets; all trigger tests pass (the 16 old failures are gone).

## Phase E: trust and operations

- [ ] **Step 17. Observability and audit trail** *(built, waiting for your review)*
  - Per call and per case: who asked, which flow, which tools, which sources, why a rate or clause was chosen, who approved what. Queryable and exportable.
  - **Done when:** any output can be traced back to its inputs and approvals.
  - Built: one audit row per call, a hash-chained log (`audit.verify`), `waku/nam/trace.py` behind `GET /v1/nam/cases/{id}/trace` (`?format=jsonl` to export) and `GET /v1/nam/runs/{run_id}`; per-user rate limiting (`WAKU_NAM_RATE`, 429).
- [ ] **Step 18. Evaluation suite** *(built, waiting for your review)*
  - Routing accuracy, retrieval quality, clause-omission rate, cross-document consistency, schema validity, injection resistance, end-to-end cases. Deterministic evals offline, judge evals with a model.
  - **Done when:** the suite runs in CI and a report shows each metric.
  - Built: `make nam-eval`, `scripts/nam_eval_report.py` (also a CI step), thresholds in `test_nam_metrics.py`. Retrieval recall runs only against a live KG (`WAKU_NAM_EVAL_KG_URL`, Step 13), uncited facts are measured offline, and there are no judge evals because no flow drafts text with a model.
- [ ] **Step 19. Integration guide and hand-over** *(built, waiting for your review)*
  - docs/nam/integration.md: the client/config file, auth setup, every endpoint with examples, error codes, and how the backend calls it from many places.
  - **Done when:** the backend team can plug it in from the guide alone.
  - Built: `docs/nam/integration.md`; `test_nam_client_e2e.py` drives a case to NIT with the guide's client alone.
