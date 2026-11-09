---
name: autonomous-work
description: Autonomous multi-step work: checklist plan, execute each step, verify; cite source, evidence, facts, figure; tool failed, timeout, retry, unavailable service, fallback; final report, status update, done, open items.
---

Plan: number the steps (one action and its tool each, no more than needed); do them in order; verify each from the tool's own output and mark it done, failed or blocked. Blocked (input, approval, permission): stop and ask exactly what unblocks it.

Facts: every figure, name, date and id comes from a tool, a document or the user, with its source (PUR id, document + page, tool). Re-read the output for the exact number and unit before quoting. Two sources disagree: show both. Mark inferences ("estimated from").

| tool outcome | do |
|---|---|
| timeout, unavailable | retry once; then "could not reach <service>", never "none found" |
| retryable error | retry once, same input |
| rejected input | fix it from the error; never resend unchanged |
| empty | that is the answer: "none found in <source>" |
| partial | use it; say what is missing |

Try another tool that answers the same question before giving up; never cover a failed lookup from memory.

Report: outcome first (done, partly, blocked); done items with verified results; failures with the error as given; what the user must decide; next action. Short, tables for numbers, nothing unverified.
