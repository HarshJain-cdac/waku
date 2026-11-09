Main recommendation: decide memory per piece of information, by asking who owns the truth for it, how long it must live, whether the model needs it every turn, and what happens if it's wrong. The answers place it in one of six layers:

- the prompt itself;
- the conversation;
- the workflow state;
- an artifact store;
- long-term memory;
- an external source such as the knowledge graph.

The guide follows one example throughout: case NAM-2026-0001 for gaskets, interrupted by "i need gate valves".

What it covers

1. The layers, and the questions that decide which one each item belongs in, with a table placing every NAM item.
2. What goes into the prompt each turn, in what order, so the provider can cache the stable parts.
3. When to write memory, when to read it, and how to update or forget it, with the published numbers behind each rule.
4. Workflow state versus conversation: checkpoints, resuming, and versioned approvals.
5. Ways to keep the prompt small, cheapest first, and the risks of summaries.
6. Keeping users, chat threads and cases separate.
7. Published attacks on stored memory, and defences that rely on structure.
8. The memory benchmarks and the tests Waku runs.
9. Waku and NAM checked against the guide: what already matches, and the gaps.

Gaps it found in Waku, most important first

1. Long-term facts are overwritten or deleted, with no record of when they were true.
2. The step that turns chat into long-term facts reads tool output too, so a malicious tender text could become a remembered fact.
3. That step adds new facts without checking them against existing ones.
4. One agent answers every chat in turn.
5. No test checks what the chat still remembers after old turns drop out of the history.
6. The current time sits mid-way through the system prompt, which stops the provider caching most of it.
7. Long-term facts aren't tied to a user or tenant.







# Deciding memory for an agent harness

An agent harness should decide memory per piece of information, not per
product. For each thing the agent might need later, the harness answers four
questions:

1. Who owns the truth for it?
2. How long must it live?
3. Must the model see it on every turn?
4. What happens if it is wrong?

The answers place the item in one of six layers:

- the prompt itself;
- the conversation;
- the workflow state;
- an artifact store;
- long-term memory;
- an external source.

This document gives that procedure, the evidence behind it from about 80
published sources, and how Waku and its NAM harness apply it today.

One example runs through the whole document. An officer opens the case
NAM-2026-0001 by typing "i need gaskets", answers "Spiral wound" to the first
follow-up question, and then types "i need gate valves" halfway through. The
right answer is a question: "NAM-2026-0001 (gaskets, step 1f: Follow-up
questions answered) is still going. Start a new case for gate valves, or carry
on with NAM-2026-0001?"

Getting that one reply right needs four kinds of memory working together:

- the open case and its stage (workflow state);
- the chat's open question (conversation state);
- the last few messages (the conversation window);
- the officer's own words (the transcript).

None of them is "the memory".

## Contents

1. [The layers](#1-the-layers)
2. [Deciding where an item goes](#2-deciding-where-an-item-goes)
3. [What enters the prompt on each turn](#3-what-enters-the-prompt-on-each-turn)
4. [Writing memory](#4-writing-memory)
5. [Reading memory](#5-reading-memory)
6. [Updating and forgetting](#6-updating-and-forgetting)
7. [Workflow state is not conversation](#7-workflow-state-is-not-conversation)
8. [Compaction and the token budget](#8-compaction-and-the-token-budget)
9. [Users, threads and cases](#9-users-threads-and-cases)
10. [Memory security](#10-memory-security)
11. [Testing memory](#11-testing-memory)
12. [Waku and NAM against this guide](#12-waku-and-nam-against-this-guide)
13. [Sources](#13-sources)

## 1. The layers

Research and vendor documentation converge on the same small set of layers.
CoALA names working, episodic, semantic and procedural memory [S2]. LangGraph
splits thread-scoped short-term memory from cross-thread long-term memory
[V19, V20]. Letta sorts by size and importance into memory blocks, files,
archival memory and external RAG [V38]. Hu et al. argue that "short-term" and
"long-term" are not modules at all. In their view, the two terms only describe
when memory is formed, evolved and retrieved [S4].

The table below is the working taxonomy this guide uses.

| Layer                         | What it holds                                                      | Lifetime              | Who writes it                                    | In the running example                                                         |
| ----------------------------- | ------------------------------------------------------------------ | --------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------ |
| **L0 Instructions**     | System prompt, rules, tool definitions, skills                     | Release to release    | Developers, sometimes the agent with approval    | `SOUL.md`, the NAM policy files, the skill files                             |
| **L1 Pinned context**   | Small facts the model needs every turn                             | Session or longer     | The harness                                      | "The officer has NAM case NAM-2026-0001 open, stage S1, next step 1g"          |
| **L2 Conversation**     | Recent messages and short tool notes                               | One thread            | The harness, every turn                          | "i need gaskets", the follow-up question, "Spiral wound"                       |
| **L3 Workflow state**   | Stage, gates, pending approvals, open question, artifacts          | Until the case closes | The harness only, never free text from the model | `nam_cases` row, its `workflow`, `followups.pending`, `nam_chat_state` |
| **L4 Artifact store**   | Large outputs kept outside the prompt and referenced by id or path | The task or longer    | Tools                                            | The quantity sheet with 960 lines, the estimate, the PR sheet                  |
| **L5 Long-term memory** | Facts about the user, episodes, reflections                        | Months                | A background job, gated                          | "The officer prefers estimates in lakh"                                        |
| **L6 Raw transcript**   | Every message, verbatim, searchable                                | Retention policy      | The harness                                      | `chat_log`                                                                   |
| **L7 External truth**   | Systems of record the agent queries                                | Owned elsewhere       | Other systems                                    | The tender knowledge graph, SAP                                                |

Two layers are easy to get wrong. L3 is not memory in the chat sense: it is
state that must survive crashes and must never be paraphrased. L7 is not
memory at all. A fact the knowledge graph owns must be fetched again, never
remembered. Waku's `SOUL.md` already says this: "Do not save claims about
graph CONTENTS as durable facts."

## 2. Deciding where an item goes

Ask the questions in this order. The first answer that applies decides the
layer.

1. **Does another system own the truth?** Then the item belongs in L7. Store
   only a reference: the tender id PUR-4, never "PUR-4 was awarded at 400".
   Prices, awards and specifications change in the source, and a remembered
   copy goes stale silently.
2. **Does a later step depend on it, or would a restart lose a decision?**
   Then it is workflow state (L3). This covers the stage, the approvals, the
   chosen precedent, the open question and the quantity sheet. Store it in a
   structured record with a version, and write it only through code. The
   Anthropic harness for long-running agents keeps its feature list as JSON
   for this reason: models are less likely to overwrite JSON inappropriately
   than Markdown [V2].
3. **Is it large?** Then it goes to the artifact store (L4), and the prompt
   gets a pointer. Manus keeps the URL when it drops a page, so the
   compression can be undone [V47]. ReadAgent keeps a short gist and looks up
   the original page when it needs detail [S18]. A 960-line quantity sheet
   never enters the prompt. The model sees "960 lines, 866 incomplete" and
   calls a tool for a line.
4. **Is it small and needed on every turn?** Then pin it in L1, at the start
   or the end of the prompt. Models use the start and the end of a long
   context best, and the middle worst [S27]. Claude Code keeps its memory
   index to 200 lines because longer files reduce adherence [V8].
5. **Is it only about this conversation?** Then it stays in L2, inside a
   bounded window, and the full text stays in L6.
6. **Is it durable and about the user, their people or their preferences?**
   Then a background job may write it to L5. Store it with its source and
   date, as a narrow item rather than one big profile [V19, V24].
7. **Is it a proven way of doing something?** Then it is a candidate skill
   (L0). It should be written only after it succeeded [S10], and only with a
   person's approval. CoALA calls writing procedural memory the riskiest kind
   of learning [S2].
8. **Is it a secret or personal data?** Then it does not go into any memory
   the model can retrieve. MIRIX keeps a separate vault [S22]. Mem0's own
   documentation says never to store credentials [V41].

Applied to the running example, the procedure gives this placement.

| Item                                                                  | Layer                          | Why                                                    |
| --------------------------------------------------------------------- | ------------------------------ | ------------------------------------------------------ |
| "PUR-4 is a past gasket tender"                                       | L7                             | The knowledge graph owns it                            |
| NAM-2026-0001 is at stage S1, step 1f                                 | L3                             | The next step depends on it                            |
| The open question "What type of gasket do you need?" with its options | L3 (`followups.pending`)     | The next message is read as its answer                 |
| "This chat is working on NAM-2026-0001"                               | L3 (`nam_chat_state.case`)   | A second case must not replace it silently             |
| "A new need, gate valves, is waiting for start-or-continue"           | L3 (`nam_chat_state.switch`) | The next message is read as the choice                 |
| The last 12 exchanges                                                 | L2                             | The model needs the conversational thread              |
| The quantity sheet                                                    | L4 (case artifact)             | It is large and it is a record                         |
| "The officer works in the Mechanical department"                      | L5                             | It is durable, about the user, and not owned elsewhere |
| How to read a BOQ                                                     | L0 (skill)                     | It is procedure, written by people                     |

## 3. What enters the prompt on each turn

The prompt is a budget, not a container. Anthropic calls context "a finite
attention budget" and asks for "the smallest set of high-signal tokens" [V1].
Chroma tested 18 models and found that performance falls as input grows, even
on simple tasks. On the same LongMemEval questions, focused prompts of about
300 tokens beat full prompts of about 113,000 tokens [S28]. LongMemEval
measured GPT-4o at 60.6% with the full history and 87.0% with only the
evidence [S32].

### Assembly order

Put the stable parts first, so the provider can cache them, and the changing
parts last. Claude's prompt cache matches an exact prefix in the order tools,
system, messages. A cache read costs a tenth of the base price or less [V11].
Manus reports that agent input runs about 100 times its output, which makes
the cache hit rate the main cost lever [V47].

1. Tool definitions. Keep them fixed for the whole session. Manus masks tools
   it does not want used instead of removing them, because removal breaks the
   cache [V47].
2. Instructions (L0).
3. Pinned context (L1): the case, its stage and what it still needs.
4. The conversation window (L2), oldest first.
5. Retrieved long-term memory (L5), only when the gate says so. Change it
   every turn and place it late [V11, V26].
6. The user's message.

Timestamps belong after the last cache breakpoint. A second-precise clock at
the top of the system prompt invalidates the cache on every turn [V47].

### Budgets in practice

| System                       | Budget rule                                                                                                                  |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| MemGPT                       | Warns the model at 70% of the window, evicts about 50% at 100%, and keeps a recursive summary of what it evicted [S8]        |
| LlamaIndex                   | 30,000 tokens in all, 70% for chat history, flushes 3,000 tokens at a time to long-term memory [V26]                         |
| Anthropic context editing    | Clears old tool results at 100,000 input tokens and keeps the last 3 tool uses [V5]                                          |
| OpenAI cookbook              | Keeps the last N turns verbatim plus a summary of at most 200 words [V15]                                                    |
| Claude Code after compaction | Re-reads at most 5 recent files, each capped at 5,000 tokens [V9]                                                            |
| Waku | The last 12 exchanges (`WAKU_HISTORY_TURNS`), each with a short note of the tools it used |

## 4. Writing memory

**Write state in code, write knowledge in the background.** Workflow state is
written by the harness the moment it changes, inside a transaction, and never
by the model's prose. Long-term facts are better written in the background:
LangMem reports higher recall from background formation, and it costs the
user no latency [V24]. Writing on the hot path is fresh but slows the turn and
splits the model's attention [V19]. Letta's sleep-time agents rewrite memory
while the user is idle. The sleep-time compute paper measured about 5 times
less test-time compute for the same accuracy [S26, V39].

**Gate the write.**

- Generative Agents scores each memory's importance from 1 to 10 when it is
  written [S7].
- Voyager stores a skill only after a critic confirms it worked [S10].
- Mem0 compares each candidate fact with the 10 most similar stored memories,
  then chooses ADD, UPDATE, DELETE or NOOP [S19].

Waku's consolidation runs once every 6 exchanges by default
(`WAKU_CONSOLIDATE_EVERY`). It asks a small model for facts "worth
remembering in a month" plus one episode sentence.

**Keep the raw record next to the derived one.**

- LongMemEval found that replacing raw rounds with extracted facts loses
  information. Using the facts to index the raw rounds instead raised recall
  by 9.4% [S32].
- Zep keeps every raw episode as provenance for the facts it extracts [S20].
- Waku keeps every message in `chat_log`, whatever consolidation extracts.

**Record where and when.** Every stored item should carry its source, its
time and its scope (user, case, thread). MemOS bundles provenance and version
with each memory unit [S21]. Zep stores two times on every fact: when it
became true, and when the system learned it [S20]. The NAM harness writes
every action to a hash-chained audit log (`nam_events`), which is the
strongest form of this rule.

**Do not let untrusted text trigger a memory write.** Section 10 covers this
rule.

## 5. Reading memory

**Decide whether to read at all.** A retrieval that is not needed costs
tokens and can mislead. Waku's retrieval gate asks a small model whether a
message needs stored memories, and it fails open.

**Read on demand when the model is strong, preload when it is not.** MemGPT
lets the model page memory in with function calls. That worked with GPT-4
(92.5% on DMR) but much less well with GPT-3.5 (66.9%) [S8]. Google ADK
offers both: `preload_memory` on every turn, or `load_memory` when the agent
decides [V30]. A harness that serves a small local model should not depend on
the model choosing to look things up.

**Retrieve few and rank well.**

- Lost in the Middle found that more than 20 retrieved documents added only
  about 1% accuracy while cost kept rising [S27].
- Generative Agents ranks by recency, importance and relevance, each scaled
  from 0 to 1 [S7].
- Zep fuses cosine similarity, BM25 and graph search, then reranks [S20].
- The best items go first or last in the block, never in the middle [S27].

**Present memory as data, with structure.** LongMemEval gained up to 10
points by formatting memory as JSON and asking the model to note what each
item says before answering [S32]. Retrieved text should be marked as data. The
NAM harness wraps it in `<untrusted>` tags (`guard.wrap`), so instructions
inside it are not followed.

**Prefer fresh facts from the source of truth over remembered ones.** Waku's
`SOUL.md` tells the model that a live tool result outranks a remembered
claim.

## 6. Updating and forgetting

**Invalidate, do not overwrite.** When a fact changes, close the old one and
add the new one with a time. Zep sets an end time on the contradicted edge
instead of deleting it [S20], and Mem0's graph variant marks it invalid
[S19]. The history then still answers "what did we use before?".

**Update in small pieces, not by rewriting everything.** ACE watched a
memory context of 18,282 tokens get rewritten down to 122 tokens. Accuracy
fell from 66.7 to 57.1, below the 63.7 the agent scored with no memory at
all. The fix was itemised entries with ids, written as deltas and merged by
ordinary code [S25].

**Expect multi-step updates to fail.** MemoryAgentBench found that no system
it tested got more than 28% right when a later fact must override an earlier
one through a chain of reasoning [S36]. A harness should keep facts that
change often (a case's stage, a line's rate) in workflow state, where code
updates them exactly, not in free-text memory.

**Forget on purpose.**

- Generative Agents decays recency by 0.995 per hour [S7].
- MemoryBank models an Ebbinghaus forgetting curve [S11].
- Neither paper validates its constants on a benchmark, so treat any decay
  rate as a setting to tune.
- The practical rules are simpler: expire files that nobody has opened in a
  long time [V4], set a retention policy on checkpoints [V20], and bound
  every index [V8].

**Label superseded information in summaries.** OpenAI's session-memory
cookbook asks the summariser to check for contradictions, let the latest
update win, quote ids exactly, and mark anything unstated as unverified
[V15].

## 7. Workflow state is not conversation

A procurement case, a coding task or an approval chain has a position that
must be exact. The position must survive a restart, and it must never depend
on what the model remembers. The vendor guidance on this point is the most
consistent in the whole survey.

- **Checkpoint every step.** LangGraph writes a checkpoint at every step, and
  a node that succeeded is not re-run on resume. It offers three durability
  modes, and only the synchronous one survives a crash mid-run [V21].
- **Resume from the checkpoint, not from the start.** Anthropic's research
  system resumes from where the agent was when an error happened [V3].
- **Assume interruption.** The Claude memory tool's injected prompt says:
  "ASSUME INTERRUPTION: Your context window might be reset at any moment"
  [V4].
- **Make side effects idempotent.** LangGraph re-runs a node from its start
  when it resumes after an interrupt [V22]. OpenAI says approval is not
  exactly-once, so side effects need idempotency keys and a check after a
  crash [V17].
- **Version the state.** OpenAI's run-state guidance asks for a version
  marker on pending state [V17]. Every write to a NAM case is a new version,
  and a write based on an older version is refused (`case.Stale`).
- **Keep harness-only state out of the prompt.** The OpenAI Agents SDK never
  sends its run context to the model [V16].

The running example shows why this matters for chat. Before, Waku kept the
chat's open question in process memory, and a restart lost it. Now the case
lives in `state.db` (`waku/nam/case.py`), linked to the chat that opened it,
and the agent reads it in its prompt every turn (`waku/nam/flow.py`): the
need, the records still in, the answers, the open question, the estimate
and the PR. "Resume NAM-2026-0001" (`nam_case`) moves the chat to another
case.

## 8. Compaction and the token budget

Use the lightest technique that keeps the prompt within budget. The ladder
below runs from the cheapest and safest technique to the most invasive. The
order follows Anthropic's own framing, where clearing old tool results is the
"lightest" form [V1].

1. **Clear or mask old tool output.** JetBrains replaced tool outputs older
   than 10 turns with a placeholder and kept the model's reasoning. That
   halved cost and solved as many tasks as LLM summarisation did [S30].
   Anthropic's context editing alone cut tokens by 84% in a 100-turn search
   evaluation [V7].
2. **Trim to a window.** Trimming is deterministic and costs no model call.
   Its weakness is abrupt amnesia [V15]. Waku trims to its last 12
   exchanges; older turns come back only through long-term memory.
3. **Summarise with fixed sections.** Factory tested compaction on more than
   36,000 messages from real sessions. A summary with fixed sections (intent,
   file changes, decisions, next steps) that only summarises the newly
   dropped turns scored best. Every method tested lost track of which files
   it had touched, so Factory recommends a separate index for artifacts
   [S31].
4. **Offload to files or records** with a pointer left behind [V47].
5. **Isolate in a sub-agent** that returns a 1,000 to 2,000 token summary
   [V1, V3].

Summaries carry risks that masking does not.

- JetBrains found that LLM summaries made agents run 13% to 15% longer [S30].
- A recursive summary scored only 35.3% on DMR in the Zep paper [V42].
- Summaries can carry a hallucination forward into every later turn [V15,
  V48].

Measure tokens per finished task, not compression ratio, because
over-compressing forces the agent to fetch the same data again [S31].

## 9. Users, threads and cases

**Scope every record.** Every framework surveyed keys memory by a scope:

- OpenAI by `session_id` [V12];
- LangGraph by `thread_id` and a store namespace such as `(user_id, "memories")` [V19];
- ADK by `user:` and `app:` prefixes [V29];
- AgentCore by `actorId` and `sessionId` [V33];
- Mem0 by `user_id`, `agent_id` and `run_id` [V41].

For NAM, the scopes are the tenant, the user, the chat thread and the case.

**A session id is not an identity.** OpenAI states this directly: the session
id selects history but does not authenticate anyone [V12]. In NAM,
authentication and roles come from another component (plan D4). The harness
only consumes the trusted identity it is given and enforces the workflow's
permissions with it.

**Shared memory is a deliberate channel.** AgentCore warns that reflections
across actors can leak one user's information to another [V35]. MINJA showed
that an ordinary user can plant a memory record that later fires on another
user's query [S37]. Long-term memory should be per user by default, and
anything shared should be reviewed.

**One process serving many chats needs care.** Waku's dashboard runs one
agent behind a lock and switches its session per request. Each switch
reloads the thread's last 12 exchanges from `chat_log`. This is correct, but
it serialises every chat turn on the server. A multi-officer deployment
should give each request its own session object over the same store.

## 10. Memory security

Memory turns a one-time prompt injection into a lasting one. The published
attacks are practical.

| Attack            | What it does                                                                                 | Result                                                        |
| ----------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| MINJA [S37]       | A normal user's queries plant a malicious reasoning record that later fires for another user | 98.2% injection success, 76.8% attack success                 |
| AgentPoison [S38] | An optimised trigger retrieves poisoned demonstrations                                       | Over 80% attack success with under 0.1% of records poisoned   |
| SpAIware [S40]    | Text in a web page makes the assistant call its memory-write tool                            | The instruction persists into every later chat and leaks data |
| MEXTRA [S39]      | Crafted prompts extract stored user queries                                                  | 50 of 200 stored queries extracted from one agent             |

The tested defences are weak. MINJA's detection prompt caught the attack on
one agent and none on the others. A general detection prompt flagged 34 of 50
benign queries [S37]. A harness should therefore rely on structure rather
than on detection:

1. Do not let content from a tool, a document or a web page trigger a memory
   write. A memory write should come from the user's own words or from code
   [S40, V36].
2. Keep long-term memory per user, and keep the number of retrieved items
   small [S39].
3. Store provenance and version on every record, so a poisoned entry can be
   found and rolled back [S21, S20].
4. Keep skills and instructions read-only at runtime. Change them only
   through a reviewed path [S2, S10].
5. Let users see and delete what is remembered about them [S40].

Waku follows rules 3 and 4 in NAM:

- the audit log records every NAM action;
- the NAM skills ship with the code;
- Waku's default `SOUL.md` allows `create_skill` only after the user says yes.

Waku also follows rule 1 for long-term facts. Consolidation sends the
assistant's replies to the summarizer cut to 200 characters and marked as
context. It keeps a fact only when at least half of the fact's content words
are the user's own, so a malicious tender text in a tool's output cannot
become a remembered fact.

## 11. Testing memory

**Public benchmarks show which failures to test for.**

| Benchmark              | Measures                                                                                                                                      | Caveat                                                                               |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| DMR [S8]               | Recall of facts from earlier sessions                                                                                                         | Saturated at 93% to 98%; the whole history fits in a modern window [S20]             |
| LoCoMo [S33]           | About 300 turns over up to 35 sessions; single-hop, multi-hop, temporal and adversarial questions                                             | About 9,000 tokens, so full context still scored best in the Mem0 paper (72.9) [S19] |
| LongMemEval [S32]      | 500 questions on extraction, multi-session reasoning, temporal reasoning, knowledge updates and abstention, at 115,000 and 1.5 million tokens | The strongest public test of updates and abstention                                  |
| MemoryAgentBench [S36] | Retrieval, learning at test time, long-range understanding, selective forgetting                                                              | No method passed 28% on multi-hop forgetting                                         |

**A harness also needs its own deterministic tests.** These tests check the
memory behaviours the harness promises, offline and with a scripted model.
Waku's tests for the running example live in
`evals/deterministic/nam/test_nam_chat_flow.py`:

- a new need typed mid-capture is asked about, and no case starts;
- starting the new case keeps the old one, and "resume" returns to its open
  question;
- the open question survives a fresh process over the same database;
- a question of the officer's own is not taken as an answer, and the open
  question comes back after the model's reply.

**Probe after every compaction.** Factory asks four kinds of questions after
compressing a session [S31]:

- recall: a fact;
- artifact: which files changed;
- continuation: resume the task;
- decision: why a choice was made.

The same four probes fit a NAM case: the chosen precedent, the quantity
sheet's lines, the next step, and why a flagged rate was accepted.

**Report cost with accuracy.** Full context can win on accuracy and still
lose by ten times on latency [S19]. Each memory change should report tokens
per turn and p95 latency next to its pass rate.

## 12. Waku and NAM against this guide

**What already follows the guide**

| Practice                                                | Where Waku does it                                                                        |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Workflow state lives in code, not in chat               | the NAM case store and the gates of each step (`waku/nam/case.py`, `waku/nam/stage_tools.py`) |
| Versioned writes                                        | a write based on an old case version is refused (`case.Stale`)                          |
| Chat position survives a restart                        | `waku/nam/case.py`                                                                      |
| The case is in the prompt every turn                    | `waku/nam/flow.py` `guide()`                                                            |
| Bounded conversation window | the last `history_turns` exchanges (`waku/app.py`) |
| Short tool notes instead of full tool output in history | `tools_note`, 160 characters per tool                                                   |
| Gated retrieval | `memory/retrieval_gate.py` |
| Raw transcript kept beside extracted facts              | `chat_log` with consolidation into `facts` and `episodes`                           |
| Large records referenced, not pasted                    | Quantity, estimate and PR sheets as case artifacts                                        |
| External truth fetched, not remembered                  | `SOUL.md` rules on the knowledge graph                                                  |
| Untrusted text marked as data                           | `guard.wrap`                                                                            |
| Hash-chained audit of every action                      | `waku/nam/audit.py`                                                                     |

**Closed since this guide was first written**

- **Facts keep their history.** An update moves the old version into
  `fact_history` with the time it was true, and the fact keeps its id.
  `manage_memory` has a `history` action that shows what a fact said before.
  Deleting a fact forgets its history too [S20, S19].
- **Facts come only from the user's words.** Consolidation applies the rule
  from section 10 [S40].
- **Consolidation reconciles before it writes.** Each new fact is compared
  with the 5 stored facts most like it. The same fact again is skipped, a
  changed fact with the same subject replaces the stored one, and anything
  else is added. Word overlap in code makes this decision, so it costs no
  model call [S19]. The tests are in
  `evals/deterministic/test_memory_reconcile.py`.

**Gaps, in the order worth closing**

1. **One agent serves every chat in turn.** Per-request sessions over the
   shared store would let two officers chat at once (section 9).
2. **No probe test runs after the history window drops turns.** Recall,
   artifact, continuation and decision probes on a long scripted NAM chat
   would catch silent forgetting [S31].
3. **The current time sits in the middle of the system prompt.** It comes
   right after `SOUL.md` and before the case and memory blocks, so everything
   after it changes every minute. Moving the clock to the end would let a
   provider cache more of the prefix [V11, V47].
4. **Facts are not scoped per user or tenant.** A multi-tenant deployment
   needs the scope on every row before long-term memory is shared [V12, V41,
   S37].
5. **Only the SQLite store keeps fact history.** The hosted backends (Mem0,
   Zep, Supabase, LangMem) still update in place, and `manage_memory` says so
   when asked for a history.

## 13. Sources

Sources marked "abstract" were read at the abstract level only. Vendor
results marked "self-reported" were not independently reproduced.

### Research and techniques

- [S1] Zhang et al., "A Survey on the Memory Mechanism of Large Language Model based Agents", 2024. https://arxiv.org/abs/2404.13501
- [S2] Sumers, Yao, Narasimhan, Griffiths, "Cognitive Architectures for Language Agents" (CoALA), 2023. https://arxiv.org/abs/2309.02427
- [S3] Wu et al., "From Human Memory to AI Memory: A Survey on Memory Mechanisms in the Era of LLMs", 2025 (abstract). https://arxiv.org/abs/2504.15965
- [S4] Hu, Liu et al., "Memory in the Age of AI Agents: A Survey", 2025. https://arxiv.org/abs/2512.13564
- [S5] LangChain, "Memory" concepts. https://docs.langchain.com/oss/python/concepts/memory
- [S6] Anthropic, "Effective context engineering for AI agents", 2025. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- [S7] Park et al., "Generative Agents: Interactive Simulacra of Human Behavior", 2023. https://arxiv.org/abs/2304.03442
- [S8] Packer et al., "MemGPT: Towards LLMs as Operating Systems", 2023. https://arxiv.org/abs/2310.08560
- [S9] Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning", 2023. https://arxiv.org/abs/2303.11366
- [S10] Wang et al., "Voyager: An Open-Ended Embodied Agent with Large Language Models", 2023. https://arxiv.org/abs/2305.16291
- [S11] Zhong et al., "MemoryBank: Enhancing Large Language Models with Long-Term Memory", 2023. https://arxiv.org/abs/2305.10250
- [S12] Xu et al., "A-MEM: Agentic Memory for LLM Agents", 2025. https://arxiv.org/abs/2502.12110
- [S13] Gutiérrez et al., "HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models", 2024 (abstract). https://arxiv.org/abs/2405.14831
- [S14] Sarthi et al., "RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval", 2024 (abstract). https://arxiv.org/abs/2401.18059
- [S15] Qian et al., "MemoRAG", 2024 (abstract). https://arxiv.org/abs/2409.05591
- [S16] Wang et al., "Augmenting Language Models with Long-Term Memory" (LongMem), 2023 (abstract). https://arxiv.org/abs/2306.07174
- [S17] Liu et al., "Think-in-Memory", 2023 (abstract). https://arxiv.org/abs/2311.08719
- [S18] Lee et al., "A Human-Inspired Reading Agent with Gist Memory of Very Long Contexts" (ReadAgent), 2024 (abstract). https://arxiv.org/abs/2402.09727
- [S19] Chhikara et al., "Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory", 2025 (self-reported baselines). https://arxiv.org/abs/2504.19413
- [S20] Rasmussen et al., "Zep: A Temporal Knowledge Graph Architecture for Agent Memory", 2025. https://arxiv.org/abs/2501.13956
- [S21] Li et al., "MemOS: A Memory OS for AI System", 2025 (abstract). https://arxiv.org/abs/2507.03724
- [S22] Wang, Chen, "MIRIX: Multi-Agent Memory System for LLM-Based Agents", 2025 (abstract, self-reported). https://arxiv.org/abs/2507.07957
- [S23] Yan, Ma et al., "Memory-R1", 2025 (abstract). https://arxiv.org/abs/2508.19828
- [S24] Wang, Mao, Fried, Neubig, "Agent Workflow Memory", 2024 (abstract). https://arxiv.org/abs/2409.07429
- [S25] Zhang et al., "Agentic Context Engineering" (ACE), 2025. https://arxiv.org/abs/2510.04618
- [S26] Lin et al., "Sleep-time Compute: Beyond Inference Scaling at Test-time", 2025 (abstract). https://arxiv.org/abs/2504.13171
- [S27] Liu et al., "Lost in the Middle: How Language Models Use Long Contexts", 2023. https://arxiv.org/abs/2307.03172
- [S28] Hong, Troynikov, Huber, "Context Rot: How Increasing Input Tokens Impacts LLM Performance", Chroma, 2025. https://www.trychroma.com/research/context-rot
- [S29] Wang et al., "Recursively Summarizing Enables Long-Term Dialogue Memory in Large Language Models", 2023 (abstract). https://arxiv.org/abs/2308.15022
- [S30] Lindenbauer et al., "The Complexity Trap: Simple Observation Masking Is as Efficient as LLM Summarization for Agent Context Management", 2025. https://arxiv.org/abs/2508.21433
- [S31] Factory, "Evaluating Context Compression for AI Agents", 2025 (internal evaluation). https://factory.com/news/evaluating-compression
- [S32] Wu et al., "LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory", 2024. https://arxiv.org/abs/2410.10813
- [S33] Maharana et al., "Evaluating Very Long-Term Conversational Memory of LLM Agents" (LoCoMo), 2024 (abstract). https://arxiv.org/abs/2402.17753
- [S34] Xu, Szlam, Weston, "Beyond Goldfish Memory: Long-Term Open-Domain Conversation" (MSC), 2021 (abstract). https://arxiv.org/abs/2107.07567
- [S35] DMR, introduced in MemGPT [S8] and critiqued in Zep [S20].
- [S36] Hu, Wang, McAuley, "Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions" (MemoryAgentBench), 2025. https://arxiv.org/abs/2507.05257
- [S37] Dong et al., "A Practical Memory Injection Attack against LLM Agents" (MINJA), 2025. https://arxiv.org/abs/2503.03704
- [S38] Chen et al., "AgentPoison: Red-teaming LLM Agents via Poisoning Memory or Knowledge Bases", 2024 (abstract). https://arxiv.org/abs/2407.12784
- [S39] Wang et al., "Unveiling Privacy Risks in LLM Agent Memory" (MEXTRA), 2025. https://arxiv.org/abs/2502.13172
- [S40] Rehberger, "Spyware Injection Into Your ChatGPT's Long-Term Memory (SpAIware)", 2024. https://embracethered.com/blog/posts/2024/chatgpt-macos-app-persistent-data-exfiltration
- [S41] Wei et al., "A-MemGuard: A Proactive Defense Framework for LLM-Based Agent Memory", 2025 (abstract, self-reported). https://arxiv.org/abs/2510.02373

### Vendors and frameworks

- [V1] Anthropic, "Effective context engineering for AI agents", 2025. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- [V2] Anthropic, "Effective harnesses for long-running agents", 2025. https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- [V3] Anthropic, "How we built our multi-agent research system", 2025. https://www.anthropic.com/engineering/multi-agent-research-system
- [V4] Anthropic, Memory tool. https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- [V5] Anthropic, Context editing. https://platform.claude.com/docs/en/build-with-claude/context-editing
- [V6] Anthropic, Compaction. https://platform.claude.com/docs/en/build-with-claude/compaction
- [V7] Anthropic, "Managing context on the Claude Developer Platform", 2025. https://claude.com/blog/context-management
- [V8] Claude Code, Memory. https://code.claude.com/docs/en/memory
- [V9] Claude Code, Explore the context window. https://code.claude.com/docs/en/context-window
- [V10] Anthropic, "Building effective agents", 2024. https://www.anthropic.com/engineering/building-effective-agents
- [V11] Anthropic, Prompt caching. https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- [V12] OpenAI Agents SDK, Sessions. https://openai.github.io/openai-agents-python/sessions/
- [V13] OpenAI, Conversation state. https://developers.openai.com/api/docs/guides/conversation-state
- [V14] OpenAI, Compaction. https://developers.openai.com/api/docs/guides/compaction
- [V15] OpenAI Cookbook, "Context engineering: short-term memory management with sessions". https://developers.openai.com/cookbook/examples/agents_sdk/session_memory
- [V16] OpenAI Agents SDK, Context management. https://openai.github.io/openai-agents-python/context/
- [V17] OpenAI Agents SDK, Human-in-the-loop. https://openai.github.io/openai-agents-python/human_in_the_loop/
- [V18] OpenAI Help, "How does reference saved memories work" (page blocked; read through search snippets only). https://help.openai.com/en/articles/11146739-how-does-reference-saved-memories-work
- [V18b] Rehberger, "How ChatGPT chat history memory and preferences work", 2025 (third-party reverse engineering). https://embracethered.com/blog/posts/2025/chatgpt-how-does-chat-history-memory-preferences-work
- [V19] LangChain, Memory concepts. https://docs.langchain.com/oss/python/concepts/memory
- [V20] LangGraph, Persistence. https://docs.langchain.com/oss/python/langgraph/persistence
- [V21] LangGraph, Checkpointers. https://docs.langchain.com/oss/python/langgraph/checkpointers
- [V22] LangGraph, Interrupts. https://docs.langchain.com/oss/python/langgraph/interrupts
- [V23] LangGraph, Add and manage memory. https://docs.langchain.com/oss/python/langgraph/add-memory
- [V24] LangMem, Conceptual guide. https://langchain-ai.github.io/langmem/concepts/conceptual_guide/
- [V25] LangChain, "Context engineering for agents", 2025. https://www.langchain.com/blog/context-engineering-for-agents
- [V26] LlamaIndex, Memory. https://developers.llamaindex.ai/python/framework/module_guides/deploying/agents/memory/
- [V27] Microsoft AutoGen, Memory. https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/memory.html
- [V28] Microsoft Semantic Kernel, Agent memory. https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-memory
- [V29] Google ADK, State. https://adk.dev/sessions/state/
- [V30] Google ADK, Memory. https://adk.dev/sessions/memory/
- [V31] Google ADK, Context compaction. https://adk.dev/context/compaction/
- [V32] AWS Bedrock AgentCore, Memory. https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html
- [V33] AWS Bedrock AgentCore, Memory terminology. https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-terminology.html
- [V34] AWS Bedrock AgentCore, Memory strategies. https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-strategies.html
- [V35] AWS Bedrock AgentCore, Episodic memory strategy. https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/episodic-memory-strategy.html
- [V36] AWS Bedrock AgentCore, Best practices. https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/best-practices.html
- [V37] Packer et al., MemGPT, full paper. https://arxiv.org/html/2310.08560
- [V38] Letta, Context hierarchy. https://docs.letta.com/guides/agents/context-hierarchy
- [V39] Letta, "Sleep-time compute", 2025. https://www.letta.com/blog/sleep-time-compute
- [V40] Mem0 paper, full text. https://arxiv.org/html/2504.19413
- [V41] Mem0, Memory types. https://docs.mem0.ai/core-concepts/memory-types
- [V42] Zep paper, full text. https://arxiv.org/html/2501.13956
- [V43] Zep, Concepts. https://help.getzep.com/concepts
- [V44] Cognee, Core concepts. https://docs.cognee.ai/core-concepts
- [V45] Supermemory, How it works. https://supermemory.ai/docs/concepts/how-it-works
- [V46] Chroma, "Context Rot", 2025. https://www.trychroma.com/research/context-rot
- [V47] Ji, "Context Engineering for AI Agents: Lessons from Building Manus", 2025. https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
- [V48] Breunig, "How Contexts Fail and How to Fix Them", 2025. https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html
- [V49] Liu et al., "Lost in the Middle", 2023. https://arxiv.org/abs/2307.03172
- [V50] Wu et al., LongMemEval, full text. https://arxiv.org/html/2410.10813
- [V51] Maharana et al., LoCoMo, 2024. https://arxiv.org/abs/2402.17753
