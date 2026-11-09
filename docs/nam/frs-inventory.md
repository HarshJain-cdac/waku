# NAM FRS inventory (Step 1)

Source: `Procurix.ai_NeedAssessmentModule_FRS.docx`, v4.0 Draft, text and all
7 embedded diagrams (A entry, B no-reference, C completion, Document
Generator internal flow, full end-to-end flow, Item/Wage estimate, Works
estimate). Every item has an id (F1, R3, ...) that later steps cite. "FRS x.y"
is the section in the document.

## 1. Functions (what NAM does)

| Id | Function | FRS | Inputs | Outputs | Gate |
|---|---|---|---|---|---|
| F1 | Conversational entry (chat, not a form) | 3.1.2, v2 2.1, Diagram A | free text, or a reference number (PR / PO / tender / Aarohan file / admin approval no.) | prefilled Category, Procurement type, Tender type, available info | officer confirms or corrects each |
| F2 | Replicate from a reference | 3.1.2 step 2, Diagram A | reference number | EXACT record from SAP + Aarohan; autofills scope/item, BOQ, specs, qty, rates, SCC, PQC | goes to Edit/Review (F12) |
| F3 | Need capture and classification | 2.2.2, 3.1.1 | description, justification, category, qty, required-by date, location, scope, item/service code, purpose, supporting docs | Need Record | mandatory need data complete |
| F4 | Predict fields, ask only what is not confident | 3.1.2 steps 3-5 | free text | predictions updated live per answer | Category + Procurement type + Tender type confirmed |
| F5 | Unique File Number | 3.1.1 step 5 | confirmed classification | file number tracking the whole NAM flow | - |
| F6 | Similar-case search | 3.1.1 steps 7-8, Diagram B | description or identifier | list of similar past tenders/PRs (70-80% match, not exact) | user selects, or says none; "try another" loops |
| F7 | Precedent selection by the user | 3.1.1 step 8 | the list from F6 | selected tender(s); estimate, BOQ, SCC, PQC, spec built from them, "not by AI selection alone" | user validates precedent (stage 2) |
| F8 | No-match guided form per category | Diagram B | category | distinct guided form: Goods / Services / New Works / Repetitive Works | - |
| F9 | Enterprise enrichment (SAP, Aarohan) | 2.2.3, 3.1.2 (second) | user input, item/service code | the SAP field list (E3); historical PR/PO/contract data, prior documents | missing mandatory info prompted before PR |
| F10 | Requirement and quantity finalisation | stage 3, 3.1.3 steps 2-3 | historical quantity from SAP | user-approved quantity/UoM, scope | user confirmation |
| F11 | Material/service + specification suggestion | end-to-end flow, "Need identification" | similar tenders + SAP info | suggested materials/services with specs; user adds/edits; "satisfied?" loop adds search parameters | user satisfied |
| F12 | Edit / Review screen | Diagrams A, B, C | autofilled or guided data | user edits items, qty, rate, specs | Submit / Confirm |
| F13 | Estimate: Goods (item rates) | 2.2.4, 3.1.3, Item Estimate diagram | qty, item code, dates, SOR/DSR, RC/PO data, budgetary quotations, vendor quotations (email upload) | budgetary estimate: item code, short/long text, qty, UoM, start/end date, cost centre, location, estimate | estimate approved by user |
| F14 | Estimate: Manpower / wage rate | 3.1.3 last para, Wage Rate diagram | dept, year, location, project type, category, qty, unit | per-line final rate, LS lines (PF/ESI/WCI, PPE, Tools & Tackles), reimbursable items | user retains/edits/removes |
| F15 | Estimate: Works | 3.5.1, Works Estimate diagram | detailed line items + qty, or a scope of work | line-item estimate, BOQ and SOR in SAP | user selects tender, finalises line items |
| F16 | Basis of estimate | 2.2.4, stage 4 | every rate used | recorded basis and supporting references per line | - |
| F17 | Document generation: BOQ / Estimate, SOR, SCC, Technical Spec, PQC, other in-scope docs | 2.2.5, 3.2, Doc Generator diagram | estimate, category, previous tenders (Aarohan), org templates, clause repositories | draft documents | Generate -> Check -> Review -> Approve (stage 5) |
| F18 | SCC build | 2.2.5 note, SCC lane | similar tenders (all, combined pointwise), latest dissimilar tenders (generic clauses only), stronger clauses from NRL/other PSU tenders; "is SCC required?" | SCC | user updates (audited), finalise |
| F19 | PQC build | PQC lane | previous tenders, PQC reference files; "is PQC required?"; qualification matrix if QCBS | PQC / QCBS matrix | user updates marks and criteria, finalise |
| F20 | Technical specification + technical compliances | Tech Spec lane, v1 1.2 | finalised materials/services, master spec repository | spec, technical compliance list | user adds/updates, finalise |
| F21 | BOQ build | 2.2.5 note, BOQ lane | finalised items + qty, item list, wage rate list | BOQ; new items -> identify SAP vendors, suggest vendors, user gets estimates; existing -> previous POs, escalated rate | finalise BOQ |
| F22 | Clause classification | 3.2 step 3 | clause repository | standard clauses (subcontracting, statutory compliance, SOR, price variance, taxes and duties) vs contract-specific (contract period, scope, key manpower) | - |
| F23 | Contract-specific fields from the officer | 3.2 step 5 | finalised document info | fields collected, auto-populated into NRL template | drafter reviews, edits, approves |
| F24 | AI review of drafts | 3.2 step 7 | draft | flags ambiguous or conflicting clauses | before finalisation |
| F25 | Document metadata + clause-selection summary, versioned | 3.2 step 8 | final document | metadata, clause-selection summary, version saved | - |
| F26 | Compliance Checker (standalone) | 2.2.7 | user/department-endorsed inputs | NAM: BUILD compliance requirements (MSE reservation, OEM, technical/department); NIT: apply + commercial; bid stage: verify only | - |
| F27 | PR generation | 2.2.6, 3.2.1 | category, tender type, date opened, proposal name, estimated value, cost centre, justification, codified item list, template | PR (SAP MM via POST API, or in Procurix.ai with its own PR file no.) | missing mandatory fields shown; user reviews and confirms |
| F28 | One-click PR creation | v3 3.2 | all PR fields populated | PR created in SAP in one action | fields complete |
| F29 | Capture SAP PR number | 2.2.6, stage 7 | SAP response | PR number/status linked to the Need Record | PR created/linked |
| F30 | Validation: format | 2.3.1 | PR + documents, templates | template/structure, mandatory sections/fields, formatting | - |
| F31 | Validation: completeness | 2.3.2 | as above | mandatory PR fields, required documents, specs/qty/rates/estimates/clauses, attachments present | - |
| F32 | Validation: consistency (cross-document) | 2.3.3 | PR, BOQ, SOR, SCC, spec, PQC | aligned descriptions, qty/UoM, rates/values, delivery dates, technical/commercial info | discrepancies highlighted, user corrects, revalidates |
| F33 | Checker against manual and circulars | 3.3.1 | checklists, Procurement Manual, circulars, previous PRs/tenders, templates | checked docs, validation status, highlighted differences, versioning and audit info; clause precedence; integrity/no tampering | - |
| F34 | Compare with references and previous versions | 3.3.1 step 4 | current docs + prior versions | differences identified | corrections, re-run checks |
| F35 | Internal validation and freeze | stage 6 | all artifacts | frozen Need Assessment package version | all mandatory artifacts approved |
| F36 | Package assembly | 2.4, 2.4.1 | Cost Estimate/BOQ, SOR, spec, PQC, SCC, attachments | complete package | mandatory docs for the case present |
| F37 | Aarohan file + approval routing | 3.4.1, stage 8 | SAP PR number | procurement file created/linked in Aarohan; routed per approval workflow; ANN/approval reference and decision | required approval received |
| F38 | ANN (Administrative Approval Note) | 1.1, 2.1, 3.2 output, Diagram C | case data | ANN generated in Aarohan, or by Procurix.ai where no e-office exists | - |
| F39 | Upload of documents edited outside NAM | 2.4.2, stage 9, Diagram C | edited document incl. corrigendum | new version; accuracy score (100% no change / partial rework %); retained as training data under governance | required document updated |
| F40 | Push finalised docs to Aarohan | Diagram C, end-to-end | SOW, spec, SCC, PQC, BOQ, extra files | uploaded to Aarohan | - |
| F41 | Handoff to NIT module | 2.2, 2.4 | frozen package | package routed to NIT / Commercial Department | - |
| F42 | Feedback and audit on every user change | end-to-end flow ("take user feedback on why suggestion was changed", "Audit" on each edit loop) | every edit to a suggestion | reason for change + audit entry | - |

## 2. Workflow stages and gates (FRS 2.5 table)

| Stage | Activity | Source | Artifact | Gate |
|---|---|---|---|---|
| S1 | Need capture and classification | User + SAP + Aarohan | Need Record; category; CAPEX/OPEX; procurement type | mandatory need data complete |
| S2 | Enterprise and precedent enrichment | SAP + Aarohan | historical PR/PO/contract data; prior documents | user validates relevant precedent |
| S3 | Requirement and quantity finalisation | NAM + User | approved requirement, scope, qty/UoM | user confirmation |
| S4 | Price evidence and estimate | SAP history + approved references + User | price evidence, basis of estimate, final estimate | estimate approved |
| S5 | Document generation and checking | Generator + Checker | SOW, BOQ/SOR, spec, PQC, SCC, validation results | Generate -> Check -> Review -> Approve |
| S6 | Internal validation and freeze | NAM + functional reviewers + compliance checker | frozen package/version | all mandatory artifacts approved |
| S7 | PR creation and reference capture | SAP MM | SAP PR number/status, account assignment | PR created/linked |
| S8 | Approval file and workflow | Aarohan / e-office | procurement file, ANN/approval reference and decision | required approval received |
| S9 | User upload | User | updated document with versioning | required document updated |

Order note: the text puts PR creation after freeze (S6 -> S7). Diagram C
generates PR in SAP and ANN in Aarohan together on Submit. Section 3.5.1 says
"freezes the documents, after which NAM creates the PR in SAP". Same order.

## 3. Roles (as named in the FRS; there is no formal role table)

| Id | Role | Where | Does |
|---|---|---|---|
| U1 | Officer (user / indenting officer) | 3.1.1, 3.1.2, 3.2 | creates the requirement, confirms predictions, selects precedent, approves qty and estimate, provides contract-specific fields |
| U2 | User department | 2.2.7, v3 3.1 | endorses compliance inputs, fills PR fields |
| U3 | Authorized user | 2.2.3, 2.2.5, 2.2.6, 2.3.3 | supplies missing data, edits AI content, confirms PR, corrects validation failures |
| U4 | Drafter | 3.2 step 7 | reviews, edits and approves the document draft |
| U5 | Functional reviewers | stage S6 | internal validation before freeze |
| U6 | Commercial Officer / Commercial Department | Item Estimate diagram, 1.1, 2.2.7 | uploads Rate Contracts and POs; receives the package; adds commercial compliances at NIT stage |
| U7 | Approver(s) in Aarohan | 3.4.1, S8 | approval per the applicable Aarohan workflow |

Gap to confirm: the FRS gives no permission matrix (who may do which step).

## 4. Business rules

| Id | Rule | FRS |
|---|---|---|
| R1 | The originating route and category decide the data required, documents, rules and validation checks | 2.2.2 |
| R2 | Precedent is chosen by the user, never by AI alone; generation uses only the selected tender(s) | 3.1.1 step 8 |
| R3 | Ask a follow-up only for a field that could not be confidently predicted | 3.1.2 step 4 |
| R4 | Similarity is "70-80% match, not exact" for tender search; "Similar" rate match uses a 95% threshold with the match basis recorded | Diagram B, v1 1.1 |
| R5 | Rate hierarchy per line: Same (exact NRL SOR) -> Similar (NRL SOR or DSR, copy rate-analysis structure) -> reuse internal rate analysis from another department -> Derived / First principle (DSR DAR structure, cost components) | 3.5.1, v1 1.1 |
| R6 | Budgetary vendor quotations and previous SAP PO rates are last resort | 3.5.1 |
| R7 | Always propose the latest available rate, never the one embedded in the historical tender | 3.5.1 |
| R8 | Every rate is classified Same / Similar / Derived / First Principle; alert when falling back to DSR | v1 1.1, version history |
| R9 | DSR 2023 and DAR are reference data, not NRL-approved rates unless separately approved | v1 1.2 |
| R10 | Goods rate comparison: VARN = ((quoted basic / PO rate) - 1) x 100; VARN < 10% -> ALR, done; else if years > 1 CAGR = ((quoted/PO)^(1/yrs) - 1) x 100; years <= 1 -> manual review; CAGR > 10% -> AHR (flag), else Regular | Item Estimate diagram |
| R11 | Previous PO extraction: sort RC + PO by material code asc, doc date desc, purchasing doc desc, item sr. no desc; search RC then PO per BOQ material code; neither -> New Item | Item Estimate diagram |
| R12 | Wage: basic wage by dept/year/location/project type/category (notified / projected / fallback); + statutory 13.13% of basic + non-statutory 35-40.6% (by worker category) = gross; MDY/HR base; Sunday/holiday +15% CP (MDY); + shift/height; final rate 2 dp; x qty | Wage Rate diagram |
| R13 | Reimbursement aggregator (MDY lines): group by year + location + project type + category; PF/EDLI, ESI or WCI 2.79% (by category), PPE 5%, Tools and Tackles 5%; x mandays; round UP to nearest Rs 50,000; append as LS lines | Wage Rate diagram |
| R14 | Manpower within Works reuses the Manpower Estimator | 3.5.1 |
| R15 | Works: line items given -> validate; scope given -> find similar tenders, fetch docs from Aarohan, user selects or revises scope, pull line items from historical Estimation Excel | 3.5.1 |
| R16 | SCC = all similar tenders combined pointwise + generic clauses of latest dissimilar tenders + legally stronger NRL/PSU clauses | 2.2.5 note |
| R17 | Separate standard clauses from contract-specific ones | 3.2 step 3 |
| R18 | No mandatory clause may be omitted (master SCC/PQC repository by department and job type) | v1 1.2 |
| R19 | BOQ is created from the finished rate estimate | 2.2.5 note |
| R20 | Missing mandatory fields are identified and the user completes them before PR creation | 2.2.3, 2.2.6 |
| R21 | Compliance: build at NAM, apply at NIT, verify only at bid stage; no new requirements at bid stage | 2.2.7 |
| R22 | Validation covers format, completeness, consistency, clause precedence, attachments, manual/circulars, document integrity (no tampering) | 2.3, 3.3.1 |
| R23 | Discrepancies are highlighted; user corrects and revalidates before proceeding | 2.3.3 |
| R24 | Package is finalised only when the case's mandatory documents are present | 2.4.1 |
| R25 | Edited documents come back with corrigendum and become the latest version | 2.4.2 |
| R26 | User-edited documents may become training data, subject to data governance | 2.4.2 |
| R27 | Every user change to a suggestion records why it was changed, and is audited | end-to-end flow |
| R28 | Goods are Codified / Uncodified; Services are AMC / Repetitive / Consultancy / Manpower; Works are New vs Repetitive and Capital vs Revenue budget | Diagram B |
| R29 | QCBS evaluation needs a qualification matrix in PQC | end-to-end flow |
| R30 | ANN stays in Aarohan where it exists; Procurix.ai generates it only where no e-office exists | 2.1 |

## 5. Data entities

| Id | Entity | Fields (from the FRS) |
|---|---|---|
| E1 | Need Record (single source of truth) | links originating requirement, enterprise data, document versions, estimate and price evidence, SAP PR ref, approval ref, validation results, final package (2.5) |
| E2 | Requirement | Unique File Number; category (Goods/Supply, Services, Works); type of procurement (CAPEX, OPEX, Technical Qty-and-Rate Estimate, MRO-Triggered); originating route (Capex/New project, Opex/Repetitive, Consumption pattern, MRO, Emergency); tender type (Open, Limited, OEM, Proprietary, Nomination, SPOT, GeM, ...); description; business justification; purpose; scope of work; item code; service code; quantity; UoM; required-by date; start/end date; location; supporting documents |
| E3 | PR (SAP fields; the bulk-PR-upload Excel is the authoritative list per v3) | product/material/service lines and short text; quantity; UoM; account assignment category; item category; short text; plant; material group; delivery date; purchasing group; requisitioner; MRP controller; GL; cost centre; order; project; control code; PR type; plus PR generator inputs: date opened, proposal name, estimated value, justification, codified item list; output PR file no., SAP PR number/status |
| E4 | SAP enrichment record | description, PR type, financial category code, cost centre, budget head, other account assignment (3.1.2 table) |
| E5 | Estimate line | item/service code, short and long description, qty, UoM, rate, rate class (Same/Similar/Derived/First principle), source reference, match basis/score, amount; Goods: PO no., doc date, rate, currency, PO sr. no., source RC/PO, VARN, CAGR, class ALR/AHR/Regular; Wage: basic, allowances, gross, CP, final rate |
| E6 | Estimate | lines, total, basis of estimate, supporting references, approval status |
| E7 | Precedent / similar case | tender no., match score, documents fetched, selected by user (yes/no) |
| E8 | Procurement document | type (BOQ, SOR, SCC, Tech Spec, PQC, SOW, ANN, other), version, status (draft/approved/frozen), metadata, clause-selection summary, source template |
| E9 | Clause | text, type SCC/PQC, department, job type, standard vs contract-specific, source tender/PSU, mandatory flag |
| E10 | Validation result | dimension (format/completeness/consistency/manual), finding, highlighted difference, status, re-run history |
| E11 | Compliance requirement | type (MSE reservation, OEM, technical, department, commercial), stage built/applied/verified, endorsed by |
| E12 | Package | documents, attachments, frozen version, Aarohan file ref, approval ref and decision, NIT handoff status |
| E13 | Uploaded edited document | version, corrigendum, accuracy score, uploader, training-data flag |
| E14 | Audit entry | who, what changed, why (user feedback), when |
| E15 | Reference data | NRL SOR; CPWD DSR 2023; DAR 2023; SOR Civil 2018; SOR E&M 2025; master tech-spec repository; master SCC/PQC repository; master reimbursable-items repository; item list; wage rate list; Procurement Manual; circulars; checklists; org templates |

## 6. Outputs

BOQ / Cost Estimate, SOR, SCC, Technical Specification(s), PQC (+ QCBS
matrix), SOW, ANN, PR (SAP or Procurix.ai), SAP PR number, Unique File Number,
basis of estimate, clause-selection summary and document metadata, validation
report with highlighted differences, technical compliance list, frozen
package, Aarohan procurement file and approval decision, NIT handoff package,
audit trail, accuracy score on re-uploaded documents.

## 7. External systems

SAP MM (read history and fields; POST PR), Aarohan / e-office (previous
tenders, files, budgetary quotations; create/link file; approval routing; ANN;
upload finalised docs), Procurix.ai document repository (org SOR/DSR,
templates), NIT module (downstream), email/vendor quotation upload.
Harness scope decision already made: SAP and Aarohan are NOT connected; the
NRL knowledge graph stands in for historical tenders.

## 8. Gaps and ambiguities in the FRS itself

1. No role/permission matrix (Section 3 of this file lists names only).
2. The bulk-PR-upload Excel "incorporated" in v3 is not embedded in the
   docx; only the field names in 2.2.3 exist. Need the actual template for
   mandatory flags, lengths and code lists.
3. "Section 2.2.8" (Tech Spec, SCC, PQC preparation) is referenced in 3.5.1
   but does not exist.
4. Two sections numbered 3.1.2.
5. Similarity: 70-80% (tender search) vs 95% ("Similar" rate); how each is
   measured is not defined.
6. Emergency procurement is an originating route in 2.2.2 but not a
   "Type of Procurement" option in 3.1.1; its different rules are not given.
7. Checklists, Procurement Manual and circulars are inputs to validation but
   are not supplied.
8. Accuracy score on re-upload (Diagram C) is named but not defined.
9. "Document integrity and absence of tampering" (3.3.1): method not stated.
10. The Goods rate comparison uses "quoted basic rate", which exists only
    once a quotation is in hand; its place in the estimate flow is unclear.

## 9. SRS additions and differences

Source: `NAM_Detailed_SRS_Reorganized_v2.docx.pdf` (SRS_NAM_2026_1 v1.0,
26 pages, text and 6 diagrams). Mostly the FRS text again; below is only
what it adds or changes. Where the two disagree, this list says so; the
harness follows the SRS unless you decide otherwise.

### New or changed items

| Id | Item | SRS | Note |
|---|---|---|---|
| F43 | Package routing to NIT (stage S10) | 2.4.3, stage table | NAM -> NIT/Commercial: validated package + structured data; gate "NIT acknowledgement" |
| F44 | Structured handoff data | 2.4.3 | package carries finalised docs, structured procurement data for tender creation, PR + SAP refs, approval refs, attachments; data captured in NAM reused by NIT (no re-entry) |
| F45 | Procurix.ai e-office approval | 3.4.1 steps 4-5 | when no Aarohan: route via Procurix.ai's own approval workflow; approve per DoA, then route to NIT |
| F46 | Checker: extract and analyse, consolidate and report | 3.3.1 steps 3, 6 | extract PR fields, sections, clauses, attachments; one consolidated report (validation issues, differences, inconsistencies, compliance discrepancies) |
| F47 | Empanelment check (Works) | 3.5.1 step 7 | works inside an existing civil empanelment (rate contract): only verify the estimate is based on NRL SOR, flag unauthorised item/rate/unit substitution; no full rate analysis |
| F48 | SAP text search for estimates | SAP flow diagram | free text searched in MAKT.MAKTX, EBAN.TXZ01, EKPO.TXZ01, ESLL.KTEXT1; Goods (codified): MAKT -> EBAN (MATNR) -> EKPO (BANFN); Services and Works (non-codified): ESLL -> ESLH -> EKPO (PACKNO) -> services tab (service no., short text, qty, unit, gross price, currency); -> estimate table -> export to Excel |
| F49 | Need identification loop | overview diagram | loops until similar historical records are found; sources: past tenders, vendors, POs, award notes, AANs |
| F50 | Aarohan upload list | end-to-end diagram | Create PR in SAP -> Create File in Aarohan -> upload SCC, PQC, BOQ, QCBS file, tech spec -> NIT |
| R31 | Originating routes are Capex/New project, Opex/Repetitive, Technical Qty-and-Rate Estimation, MRO | SRS 2.2.2 | CHANGED: the FRS had "consumption pattern" and "Emergency"; the SRS has neither |
| R32 | Package cannot progress to NIT while mandatory documents, validations or approvals are incomplete | 2.4.3 | hard gate |
| R33 | NAM scope ends at handoff to NIT; NIT creation, publication, bids, evaluation, award are out of scope | 2.4.3 | boundary |
| R34 | "Similar" threshold is configurable (~95%) and the extent of dissimilarity is recorded | 3.5.1 5b | refines R4 |
| R35 | Fresh rate analysis (DAR structure) takes cost components from NRL SOR 2023, DSR Civil Vol 1 and 2 2023, DSR E&M 2022, APWD SOR (NH) 2021 (road works instead of DSR), SOR RR 2020-21, source recorded per component | 3.5.1 5d | refines R5 |
| R36 | Alert whenever a rate comes from DSR instead of NRL SOR (repeated fallback needs scrutiny) | 3.5.1 step 6 | makes R8 explicit |
| R37 | PO rate is last resort because it is a vendor's price, not an elemental cost | 3.5.1 step 6 | reason for R6 |
| R38 | Goods rate comparison: YRS = ROUND((evaluation date - PO date) / 365.25, 1); evaluation date = BOQ upload date; search ME3M_RC (rate contracts) first, then ME2M_PO, exact match; found in neither -> New Item, no comparison | Item Estimate diagram | refines R10, R11 |
| R39 | Wage: Sunday/holiday x2 first, then +15% CP (MDY only); PF/EDLI 13%, ESI 4.75% or WCI 2.79% (by category) | Wage diagram | refines R12, R13 |
| R40 | Document generator "learns from user input" at the edit step | Doc Generator diagram | ties to F39, R26 |

### Changed field lists

- E4 enrichment (SRS 2.2.3, 3.1.2): description and available
  specifications, qty and UoM, PR type, financial category/code, cost centre,
  WBS element/project code, budget head, other account assignment. SAP
  sources: EBAN (PR), EKKO/EKPO (PO), ESLH/ESLL (services). SAP is S/4HANA;
  stage 1 names SAP MM/PM/PS.
- E3 PR fields (SRS 2.2.6): item/service description, start and end date,
  qty and UoM, estimated value, PR type, delivery requirements, financial
  classification, cost centre and other account assignment, other mandatory
  PR attributes. The FRS lists the 17 SAP field names instead. Both are
  kept; the bulk-PR Excel would settle it.
- E12 package (SRS 2.4.1) adds: PR + SAP/ERP reference, ANN or approval
  reference, PR and document validation results.
- Checker inputs (SRS 3.3.1) add previous POs; comparison adds contracts.

### In the FRS but not in the SRS

Chatbot prefill flow (FRS 3.1.2), one-click PR (v3), bulk-PR Excel as the
authoritative field list (v3), the rate categories Same / Similar / Derived /
First Principle by name (v1 1.1), master data and clause repositories
(v1 1.2), requirement-gathering appendix. The harness keeps them.

### Gaps still open

The SRS closes none of the gaps in section 8. It still cites the missing
"Section 2.2.8", and still has no role/permission matrix, no PR Excel,
no checklists, manual or circulars.
