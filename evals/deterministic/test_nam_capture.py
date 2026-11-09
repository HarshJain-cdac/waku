"""NAM step 1, Need capture: the whole graph is scanned for a stated need,
matches are tiered by how related they really are, the dossier file is written,
and the need moves to References only when there is material to build from.
Offline: the KG is a stub that answers like /api/kg/*."""

import sqlite3

import pytest

from waku.tools import nam, nam_capture, nam_dossier


@pytest.mark.parametrize("text, head", [
    ("i need to procure pipes", "pipes"),
    ("AMC for housekeeping at Plant-1 for 12 months", "housekeeping"),
    ("carbon steel pipes for RTA", "pipes"),
    ("Supply of gate valves", "valves"),
    ("i need to procure pipes; 6 inch carbon steel", "pipes"),
    ("i need something; spiral wound gaskets", "gaskets"),
    ("i need something", ""),
])
def test_head_term_is_the_thing_being_procured(text, head):
    assert nam_capture.head_term(text) == head


LEXICAL = [
    {"case_key": "PUR-A", "tender_no": "T-A", "job_name": "Supply of Pipes for RTA",
     "matched_by_name": True, "matching_item_count": 9, "matching_items": ["GI pipe"]},
    {"case_key": "PUR-B", "tender_no": "T-B", "job_name": "Tubes for Furnace",
     "matched_by_name": False, "matching_item_count": 45, "matching_items": ["PIPE 4in"]},
    {"case_key": "PUR-C", "tender_no": "T-C", "job_name": "Hiring of vehicle",
     "matched_by_name": False, "matching_item_count": 1, "matching_items": ["pipe wrench"]},
    {"case_key": "PUR-D", "tender_no": "T-D", "job_name": "Drain cleaning",
     "matched_by_name": False, "matching_item_count": 2, "matching_items": ["pipe"]},
]
SEMANTIC = [
    {"pur_case_id": "PUR-D", "job_name": "Drain cleaning", "matched_items": ["drain pipe"]},
    {"pur_case_id": "PUR-E", "tender_no": "T-E", "job_name": "Boiler tubing",
     "matched_items": ["seamless tube"]},
    {"pur_case_id": "PUR-F", "job_name": "Supply of valves", "matched_items": []},
]


def test_tiers_direct_then_line_items_and_incidental_kept_apart():
    related, incidental = nam_capture.classify_tenders(LEXICAL, SEMANTIC, ["pipes"])
    tiers = {r["case_key"]: r["tier"] for r in related}
    assert tiers == {"PUR-A": "direct", "PUR-B": "line items",
                     "PUR-D": "line items",   # incidental, promoted by a semantic item match
                     "PUR-E": "line items"}   # semantic only, but it matched an item
    assert related[0]["case_key"] == "PUR-A"
    assert [e["case_key"] for e in incidental] == ["PUR-C"]
    # a nearest neighbour that matched no item is not related at all
    assert "PUR-F" not in tiers


def _counts(boq, clauses):
    return {"counts": {"boq_lines": boq, "pqc_clauses": clauses,
                       "scc_clauses": 0, "spec_clauses": 0}}


def test_readiness_needs_material_not_just_matches():
    assert not nam_capture.readiness([])["ready"]
    assert not nam_capture.readiness([{"case_key": "X", **_counts(0, 4)}])["ready"]
    assert not nam_capture.readiness([{"case_key": "X", **_counts(9, 0)}])["ready"]
    ready = nam_capture.readiness([{"case_key": "X", **_counts(9, 4)}])
    assert ready["ready"] and ready["material_cases"] == ["X"]


def _fake_kg(summaries=None, down=False):
    summaries = summaries if summaries is not None else {
        "PUR-A": {"boq_lines": 9, "pqc_clauses": 5, "scc_clauses": 6, "spec_clauses": 7}}
    calls = []

    def fetch(kg_url, path, params):
        calls.append((path, params))
        if down:
            raise OSError("connection refused")
        if path == "/api/kg/tenders":
            return {"count": len(LEXICAL), "terms": ["pipe", "pipes"], "tenders": LEXICAL}
        if path == "/api/kg/precedent":
            return {"best_similarity": 0.8, "tenders": SEMANTIC}
        if path == "/health":
            return {"tenders": 203}
        if path == "/api/kg/case_summary":
            keys = params["case_keys"].split(",")
            return {"cases": [{"case_key": k, "tender_no": f"T-{k[-1]}", **summaries[k]}
                              for k in keys if k in summaries]}
        raise AssertionError(path)

    fetch.calls = calls
    return fetch


def test_capture_writes_dossier_and_moves_to_references(tmp_path):
    conn = sqlite3.connect(":memory:")
    fetch = _fake_kg()
    # skip_followups: the follow-up questions are tested in test_nam_followup.py
    out = nam_capture.capture(conn, tmp_path, "http://kg", "i need to procure pipes", fetch=fetch,
                              skip_followups=True)

    # the lexical lane searched for the item, not the whole sentence
    assert ("/api/kg/tenders", {"query": "pipes", "limit": 100}) in fetch.calls
    assert out["stage"] == "references" and out["next_step"] == "references"
    assert [r["case_key"] for r in out["related"]][:2] == ["PUR-A", "PUR-B"]
    assert out["incidental"] == ["PUR-C"]
    assert out["category"]["id"] == "goods" and out["category"]["confident"]

    need = nam.load(conn, out["need_id"])
    assert need.stage == "references" and "PUR-A" in need.related_cases
    assert need.selected_cases == []   # found is not selected: the officer still picks

    text = (tmp_path / "nam" / f"{out['need_id']}.md").read_text()
    assert out["dossier"] == text
    assert "PUR-A" in text and "203 tenders" in text and "Ready for References" in text
    assert "Incidental mentions" in text and "PUR-C" in text


def test_refining_rewrites_the_capture_section_once(tmp_path):
    conn = sqlite3.connect(":memory:")
    first = nam_capture.capture(conn, tmp_path, "http://kg", "i need something",
                                fetch=_fake_kg())
    assert first["stage"] == "capture" and first["next_step"] is None
    assert first["readiness"]["ask"]

    second = nam_capture.capture(conn, tmp_path, "http://kg", "pipes",
                                 need_id=first["need_id"], fetch=_fake_kg(),
                                 skip_followups=True)
    assert second["need_id"] == first["need_id"] and second["stage"] == "references"
    assert second["dossier"].count("## 1. Need capture") == 1
    assert nam.load(conn, first["need_id"]).raw_text == "i need something; pipes"


def test_no_material_or_no_graph_stays_in_capture(tmp_path):
    conn = sqlite3.connect(":memory:")
    thin = nam_capture.capture(conn, tmp_path, "http://kg", "pipes",
                               fetch=_fake_kg(summaries={}))
    assert thin["stage"] == "capture" and thin["related"]

    down = nam_capture.capture(conn, tmp_path, "http://kg", "pipes", fetch=_fake_kg(down=True))
    assert down["stage"] == "capture" and "unreachable" in down["error"]
    assert "Could not scan" in down["dossier"]


def test_dossier_keeps_other_steps_and_rejects_bad_ids(tmp_path):
    kw = {"requirement": "pipes", "stage": "references"}
    nam_dossier.write_step(tmp_path, "NAM-2026-0001", "references", "ref body", **kw)
    nam_dossier.write_step(tmp_path, "NAM-2026-0001", "capture", "old", **kw)
    nam_dossier.write_step(tmp_path, "NAM-2026-0001", "capture", "new", **kw)
    text = nam_dossier.read(tmp_path, "NAM-2026-0001")
    assert "new" in text and "old" not in text and "ref body" in text
    assert text.index("1. Need capture") < text.index("2. References")
    with pytest.raises(ValueError):
        nam_dossier.write_step(tmp_path, "../../etc/x", "capture", "b", **kw)
    with pytest.raises(ValueError):
        nam_dossier.write_step(tmp_path, "NAM-2026-0001", "nonsense", "b", **kw)


def test_tool_reports_the_next_step_to_the_model(tmp_path, monkeypatch):
    conn = sqlite3.connect(":memory:")
    real = nam_capture.capture
    monkeypatch.setattr(nam_capture, "capture",
                        lambda *a, **k: real(*a, **k, fetch=_fake_kg()))
    tool = nam_capture.make_tool(conn, tmp_path, "http://kg")
    out = tool.fn(requirement="i need to procure pipes")
    # without a model, the tenders' facets decide: these four do not split
    # in any way worth asking about, so NAM moves straight on
    assert "References step" in out and "PUR-A" in out


def test_tool_hands_the_models_question_to_the_chat(tmp_path, monkeypatch):
    import json
    conn = sqlite3.connect(":memory:")
    real = nam_capture.capture
    monkeypatch.setattr(nam_capture, "capture",
                        lambda *a, **k: real(*a, **k, fetch=_fake_kg()))
    question = {"done": False, "question": "Is it for the furnace?",
                "options": [{"label": "Yes", "match": "furnace"}]}
    tool = nam_capture.make_tool(conn, tmp_path, "http://kg",
                                 ask_model=lambda system, user: json.dumps(question))
    out = tool.fn(requirement="i need to procure pipes")
    assert "Is it for the furnace?" in out and "question_id=q1" in out
