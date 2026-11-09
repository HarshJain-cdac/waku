# Dataset sources for the NAM fine-tune

Sources for fine-tuning an 8B model on the NAM flow and NRL procurement work.
Collected 2026-10-22. All paths are under `/data2/nrl_dev/Harsh` (one level above
this repo) unless shown as absolute.

The model should learn the NAM workflow, tool calling and NRL wording. Facts
(rates, tenders, PQC/SCC clauses) stay in the KG and come from tools at run
time.

## 1. Ready-made question-and-answer pairs (usable now)

| Source | Size | Use |
|---|---|---|
| `distilabel/output_full_run/procurement_qa.jsonl` | 14,272 lines | Manual rules |
| `distilabel/output_CoT/procurement_qa.jsonl` | 8,163 lines | Rules with worked reasoning |
| `distilabel/output_final/procurement_qa.jsonl` | 3,200 lines | Manual rules |
| `distilabel/output_nrl_final/procurement_qa.jsonl` | 2,752 lines | NRL manual rules |
| `augmentoolkit/Agument_data_output*` | about 340 lines | Factual, follow-up and hallucination-check training sets |

These overlap heavily: remove duplicates first. Expect well under the 28,000
raw lines.

## 2. NRL rule documents (for generating more)

- `distilabel/procurement_manuals/` and `distilabel/nrl_manual_pdfs/`: 16
  Markdown files, the Goods, Works and Services manuals (2017 / 2022 / 2025)
  plus amendment notices.
- `distilabel/Agument_data/`: 3 manual PDFs (Rev1).
- `KG/NAM_Architecture/`:
  - NRL Cost Estimation Manual (Ver.1, 17 Jun 2026), with its annexure list
    and infographic;
  - `NAM_PDF.pdf`, `nam_highlevel.docx`, `NAM_Solution_Design_Focused.docx`;
  - `SAP_screens.docx` and the AI use-cases document.

  These are the main sources for the NAM workflow, and none of them has been
  used yet.

## 3. NRL tender records (the KG corpus)

- `/data2/nrl_dev/nrl_kg_data`: 35,926 files in 209 cases (Service 25,579,
  Goods 10,345). Mostly PDF, plus xls, docx and msg emails.
- Already in the KG (NebulaGraph, read through the API on :8077): items,
  rates, bidders, PQC/SCC clauses, BOQs.
- `Mechanical Maintenance/` (33 PUR folders) and `new_extraction/`
  (17 departments).
- `KG/data/review_queue.jsonl` (20 MB) and `KG/data/item_merge_proposals.jsonl`:
  human review decisions, useful as matching and correction examples.

## 4. Waku's own behaviour

- `waku-agent/.waku/traces/`: 13 days, 2,374 events, including tool calls.
- `waku-agent/.waku/state.db`:
  - `chat_log` 786;
  - `nam_cases` 45 and `nam_case_versions` 67;
  - `nam_needs` 26 and `nam_events` 61;
  - `nit_drafts` 7 and `nam_nit_fields` 9;
  - `facts` 104 and `episodes` 29.

These are real multi-turn conversations: the best source for tool calling and
keeping track of the flow. Correct the bad turns (for example a reply that
lost track after "ok") before using them.

## 5. NAM logic in code (for generated flow conversations)

- `waku-agent/waku/nam/playbooks/`: 28 flow steps (need, classify, quantity,
  estimate, documents, approval, handoff).
- `waku-agent/waku/nam/skills/`: the `nrl-procurement` (goods / works /
  services) and `nam-documents` skills.
- Waku's tool definitions: the targets for tool-calling data.
- `waku-agent/evals/deterministic/nam/`: 43 test files of expected behaviour.
  These belong in the test set, not the training data.
- NIT template: `waku-agent/nit-forge-ui/src/lib/nit-template.ts` and
  `Doc_class/NIT_seg/`.

## 6. Other organisations' tenders (general tender wording, not NRL rules)

- `raw/` (133 vendor archives) and `raw_data/` (183 PDFs).
- `Extracted_data/` (BARC, IIT Delhi, Kanpur and Madras).
- `extrcated_data_16-07_2026/` (AAI, BHEL, BSNL).
- `outputs_batch1/` and `outputs_batch2/` (AIIMS and others).
- `data/NRL_DATA/` (AIIMS, BHEL).
- Spreadsheets: `tender_data_extracted*.xlsx`, `aai_tender_data*.xlsx`,
  `clean_data.csv`.

## 7. Generation tools

- `distilabel/`, which includes an APIGen tool-calling example
  (`examples/pipeline_apigen.py`).
- `augmentoolkit/`.
- `synthetic-data-kit/`.
- Teacher model: `gpt-oss-120b` on :3007.

## Notes

- Tender documents and chat logs contain vendor and personal details. Use the
  output of `privacy_filter` (`privacy_filter_audit.jsonl`,
  `privacy_filter_checkpoint.jsonl`) before training.
- The KG node counts are not listed here: the KG API was not running when
  this was collected. Start it with `KG/scripts/start_kg_network.sh`.
- Biggest gaps: the NAM documents (section 2) and multi-turn flow examples
  (sections 4 and 5).

## Suggested mix

| Share | Data |
|---|---|
| about 40% | Workflow and tool calling: sections 4 and 5, plus APIGen data generated from Waku's tools and KG API outputs |
| about 60% | Rules knowledge: sections 1 and 2, with duplicates removed |

Keep 10% of the conversations aside for testing, along with the NAM evals.
Compare the tuned model with the base model using
`waku-agent/scripts/llm_consistency.py`.
