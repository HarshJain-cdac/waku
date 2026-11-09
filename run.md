cd /data2/nrl_dev/Harsh/waku-agent
source /data2/nrl_dev/Harsh/waku-agent/.venv/bin/activate
waku dashboard

nohup bash -c "source /data2/nrl_dev/Harsh/waku-agent/.venv/bin/activate && waku dashboard" > waku_dashboard.log 2>&1 &

cd /data2/nrl_dev/Harsh/waku-agent && WAKU_DASHBOARD_HOST=0.0.0.0 .venv/bin/waku dashboard

cd /data2/nrl_dev/Harsh/KG
source /data2/nrl_dev/Harsh/KG/.venv/bin/activate
uvicorn webapp.server:app --host 127.0.0.1 --port 8081

cd /data2/nrl_dev/Harsh/KG && ./scripts/start_kg_network.sh --stop && ./scripts/start_kg_network.sh

cd /data2/nrl_dev/Harsh/KG && .venv/bin/uvicorn webapp.precedent_api:app --host 0.0.0.0 --port 8077

nohup bash -c "source /data2/nrl_dev/Harsh/KG/.venv/bin/activate && uvicorn webapp.server:app --host 127.0.0.1 --port 8081" > uvicorn.log 2>&1 &

cd /data2/nrl_dev/Harsh/waku-agent/nit-forge-ui/
npm run dev
nohup bash -c "cd /data2/nrl_dev/Harsh/waku-agent/nit-forge-ui/ && npm run dev" > npm_dev.log 2>&1 &

Then run each one in its own terminal. Each stays in the foreground, and Ctrl+C stops it.

Terminal 1: KG API (:8077)
cd /data2/nrl_dev/Harsh/KG && .venv/bin/uvicorn webapp.precedent_api:app --host 0.0.0.0 --port 8077

Terminal 2: KG web UI (:8081)
cd /data2/nrl_dev/Harsh/KG && .venv/bin/uvicorn webapp.server:app --host 0.0.0.0 --port 8081

Terminal 3: Waku (:7777)
cd /data2/nrl_dev/Harsh/waku-agent && WAKU_DASHBOARD_HOST=0.0.0.0 .venv/bin/waku dashboard

Both KG servers take up to a minute to load. Then share http://10.180.148.183:8081 for the KG and http://10.180.148.183:7777 for the agent.

cd /data2/nrl_dev/Harsh/KG && ./scripts/start_kg_network.sh --stop && ./scripts/start_kg_network.sh

cd /data2/nrl_dev/Harsh/KG && ./scripts/start_kg_network.sh

Context

- Harness repo: /data2/nrl_dev/Harsh/waku-agent
- Spec: /data2/nrl_dev/Harsh/waku-agent/Procurix.ai_NeedAssessmentModule_FRS.docx
  (Procurix.ai Need Assessment Module – Functional Requirements Specification)

Goal
Turn waku-agent into a strong, plug-in agent harness for the Procurix.ai
Need Assessment Module (NAM). We are NOT building the NAM frontend or backend.
The backend only adds the Waku harness API. From then on, the harness must
handle every NAM task from start to finish.

Integration model

- The Waku API is exposed through one client/config file on the backend.
- The backend can call it from many places, the same way it would call an LLM.
- Each call carries only a very small system prompt (e.g. "Assess need for
  request #123" or "Validate this requirement document"). The harness must
  work out the right NAM task from that alone. It does this with its own
  built-in NAM knowledge: FRS workflows, business rules, data schemas,
  approval stages and validations.

Requirements (the harness must be strong in all of these)

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

First step (read-only, do not change code yet)

1. Read the FRS docx fully and list every NAM function, workflow, role,
   rule, data entity, and output.
2. Read the current waku-agent codebase: architecture, agent loop, tools,
   API, security, and document handling.
3. Produce a gap analysis mapping each FRS function to what the harness has
   now, what is missing, and what is needed. Cover routing, tools, documents,
   security and API.
4. Propose an implementation plan with phases and file-level changes.
   Wait for my approval before building anything.

Working preference: give me the shell commands to run instead of running
them yourself; I will paste the output back.

# NAM Architecture Components vs Waku Today

| Component                                 | Role                                                    | What it means for NAM                                                                                                                                             | Waku today                                                   |
| ----------------------------------------- | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| **Model**                           | The reasoning and language engine.                      | Which model handles which step, for example the SLM for non-technical drafting and an external LLM for technical content.                                         | Provider config exists. No per-task routing.                 |
| **Instructions / policy**           | Persona, rules, procedure.                              | NRL rules, the Goods / Works / Services separation, and "thresholds are never final". These should be per-agent, not one shared file.                             | One global `SOUL.md`.                                      |
| **Tools / actions**                 | What the agent can do, with schemas and permissions.    | SAP read and write, Aarohan fetch and route, estimator, clause lookup, document builder, validator. Each has a side-effect class (read, write, irreversible).     | Registry and schemas only.                                   |
| **Orchestration**                   | Control flow: the loop, plus who decides the next step. | A staged workflow with gates (need → estimate → documents → PR → validation → package). Code decides the path and the model works inside each step.          | Bare loop. We hand-built the bypass for the wizard.          |
| **State / working memory**          | What this case knows right now.                         | The Need Record: one durable source of truth per requirement, separate from chat history.                                                                         | Partial (`nit_drafts`), with the two-sources-of-truth bug. |
| **Knowledge / retrieval**           | Grounding in approved material.                         | Clause library, SOR/DSR/DAR, past tenders, procurement manual, with citations and source-authority flags.                                                         | Weak.                                                        |
| **Long-term memory**                | What persists across cases.                             | Precedent history and edited documents users re-upload, subject to data governance.                                                                               | Generic facts and episodes, not shaped for this.             |
| **Guardrails**                      | Limits enforced outside the model.                      | Never auto-select a precedent, never invent a rate, block a duplicate PR, treat uploaded documents as untrusted input, hold irreversible actions until confirmed. | Prompt requests only.                                        |
| **Human oversight**                 | Approval and override points.                           | Review at quantity, estimate, clauses, documents and PR confirm, plus the Aarohan approval routing.                                                               | None.                                                        |
| **Identity and access**             | Who is acting and what they may do.                     | Officer, drafter and approver roles, and SAP data scope.                                                                                                          | None (`session_id` is only a label).                       |
| **Observability and audit**         | Record of what happened and why.                        | Basis of estimate, why a rate was classed as "Similar", which clauses were chosen, who accepted what.                                                             | Debug traces only.                                           |
| **Evaluation**                      | Measured reliability.                                   | Retrieval quality, clause-omission rate, cross-document inconsistency catch rate, SAP acceptance of generated PRs.                                                | None.                                                        |
| **Interfaces (inputs and outputs)** | How the agent perceives and delivers.                   | Chat, structured events to the frontend, document uploads, Excel and PDF ingestion, SAP and Aarohan payloads.                                                     | Chat and events exist. Ingestion is partial.                 |

strong feedback loop which should make sure it should complete the task
to do list creation, to complete a task step by step
flowless work, which should take flow automatically
make skills.md in explaining , pqc, css and what thing to extrac tand how to extract.
strong tools
