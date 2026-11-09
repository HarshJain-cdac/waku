"""NAM: the Need Assessment Module, as NRL's PR Creation Flow for goods.

The officer says what is needed; the agent works the manual's three stages
with its tools, and the harness keeps the case and checks every gate:

  flow.py         the manual's steps (1a-3b), the agent's guide each turn
  case.py         the case per chat: need, items, records, answers, estimate,
                  PR; every version kept; the acting caller's tenant
  stage_tools.py  the agent's tools, one per step, each gate in code
  narrow.py       stage 1: the records (SAP, past tenders) and the questions
                  that narrow them, checked against the data
  estimate.py     stage 2: last price, 7% a year, YRS and CAGR, the lock
  pr.py           stage 3: the PR's fields and the confirmation
  kg_mcp.py       the knowledge graph over MCP; kg_tools.py its lookup tools
  identity.py     the trusted identity context; permissions.py what it may do
  guard.py        text from outside is data, never instructions
  domain.py       the agent stays on procurement work
  answer_data.py  the KG data a reply leaves out is added in code
  audit.py        one append-only, hash-chained row per tool call and model call
"""
