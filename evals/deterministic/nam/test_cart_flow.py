"""DETERMINISTIC EVAL — the need understood, item by item, into a cart.

A job description names several materials. Each is searched in SAP at once
and counted (by short text, by long text); the officer chooses the ones that
go forward; each is narrowed to one material code and put in the cart, one
at a time; the PUR cases are ranked by how many of the materials each holds;
each cart item gets its own PR; and undo takes the officer's acts back, one
at a time, as far as they want.
"""

from __future__ import annotations

import sqlite3

import pytest

from evals.deterministic.nam.test_pr_flow import _kg
from waku.nam import case, chatstate, narrow, stage_tools

URL = "http://127.0.0.1:9/mcp"


def _line(code, desc, pur, long_text="", po="4500000001", pr="10000001", date="2024-01-10"):
    return {"description": desc, "codes": {code: desc}, "lines": [
        {"kind": "PO", "doc_no": po, "date": date, "material": code, "quantity": 4.0,
         "unit": "NOS", "rate_inr": 500.0, "pur_case_id": pur, "pr_no": pr, "po_no": po,
         "long_text": long_text}]}


# PUR-B holds all three materials; PUR-A two; PUR-C one
SAP = {
    "gasket": {"results": [
        _line("G-1", "GASKET SPW 2IN 150#", "PUR-A"),
        _line("G-1", "GASKET SPW 2IN 150#", "PUR-B", po="4500000002", date="2025-02-01"),
        _line("G-2", "GASKET SPW 4IN 300#", "PUR-C")]},
    "valve": {"results": [
        _line("V-1", "GATE VALVE 2IN", "PUR-A", "body CS flanged class 150"),
        _line("V-2", "GATE VALVE 2IN", "PUR-B", "body SS screwed class 800",
              po="4500000003", date="2025-02-01"),
        _line("V-3", "GLOBE VALVE 2IN", "PUR-C", "body CS flanged")]},
    "thermowell": {"results": [
        _line("T-1", "THERMOWELL SS316 U320", "PUR-B", po="4500000004", date="2025-02-01"),
        _line("T-2", "THERMOWELL SS316 U400", "PUR-C", "drilled bar stock",
              po="4500000005")]},
    "bolt": {"results": [{"description": "Seal plate work", "codes": {}, "lines": [
        {"kind": "SERVICE", "doc_no": "4300000001", "date": "2025-03-01", "material": None,
         "rate_inr": 100.0, "pur_case_id": "PUR-D", "long_text": "stud bolt replacement"}]}]},
}
JOB = "Overhaul of crude unit line 4: replace gaskets, gate valves and thermowells"


@pytest.fixture
def t(tmp_path):
    conn = sqlite3.connect(":memory:")
    call, _ = _kg(SAP)
    tools = {x.name: x for x in stage_tools.make_tools(conn, tmp_path, URL, call)}
    token = chatstate.enter("chat-c")
    tools["_shown"], tools["_conn"], tools["_home"] = [], conn, tmp_path
    yield tools
    chatstate.leave(token)


def _data(t):
    return case.for_session(t["_conn"], "chat-c")


def _choose_q(t):
    out = t["nam_choose"].fn(question="Which of these do you want to take forward?",
                             _notify=lambda k, e: t["_shown"].append(e))
    chatstate.mark_asked("")             # the officer answers in the next turn
    return out


def _need(t, items=("gasket", "valve", "thermowell")):
    return t["nam_need"].fn(need=JOB, items=list(items))


# -- 1c: the materials, counted in SAP -------------------------------------------------

def test_each_material_of_a_job_description_is_counted_in_sap_at_once(t):
    out = _need(t, ("gasket", "valve", "thermowell", "bolt"))
    assert "| 1 | gasket | 2 materials | 2 by short text |" in out
    assert "| 2 | valve | 3 materials | 3 by short text |" in out
    # the service line is found by its long text only, and named for what it is
    assert "| 4 | bolt | 1 service line | 1 by long text only |" in out
    assert "nam_choose" in out


def test_the_choice_question_carries_each_material_with_its_sap_count(t):
    _need(t)
    _choose_q(t)
    assert t["_shown"][-1]["options"] == ["gasket (2 materials)", "valve (3 materials)",
                                          "thermowell (2 materials)", "All of them"]
    assert stage_tools.reminder(t["_conn"], "chat-c")[0].startswith("Which of these")


def test_no_question_about_an_item_before_the_officer_chooses(t):
    _need(t)
    out = t["nam_ask"].fn(item="valve", question="Which body?", options=[
        {"label": "CS", "words": ["cs"]}, {"label": "SS", "words": ["ss"]}])
    assert out.startswith("REFUSED: The officer has not chosen which materials go forward")


def test_the_chosen_items_are_worked_one_at_a_time_in_the_officers_order(t):
    _need(t)
    _choose_q(t)
    out = t["nam_choose"].fn(items=["thermowell (2 materials)", "2"])
    assert out.startswith("Taken forward, in this order: thermowell, valve. Not taken: gasket.")
    assert "Now 'thermowell'" in out
    out = t["nam_ask"].fn(item="gasket", question="Size?", options=[
        {"label": "2IN", "words": ["2in"]}, {"label": "4IN", "words": ["4in"]}])
    assert "was not taken forward" in out
    data = _data(t)
    assert [i["name"] for i in case.chosen(data)] == ["thermowell", "valve"]
    assert case.current_item(data)["name"] == "thermowell" and data["choosing"] is None


# -- precise questions: one code at the end ------------------------------------------

def test_codes_sharing_a_short_text_are_told_apart_by_their_long_text(t):
    _need(t, ("valve",))
    digest = narrow.digest(case.remaining(_data(t)["items"][0]))
    assert "Same short text, different material codes" in digest
    assert "'GATE VALVE 2IN' (2 codes): V-1: 150, cs, flanged; V-2: 800, screwed, ss" in digest
    out = t["nam_ask"].fn(question="Which body and end?", options=[
        {"label": "CS flanged", "words": ["cs", "flanged"]},
        {"label": "SS screwed", "words": ["ss", "screwed"]}])
    assert out.startswith('Asked: "Which body and end?"')
    chatstate.mark_asked("")
    out = t["nam_answer"].fn(answer="SS screwed")
    assert "1 material still in" in out


def test_the_cart_fills_item_by_item_and_shows_the_next_one(t):
    _need(t)
    t["nam_choose"].fn(items=["valve", "thermowell"])
    t["nam_answer"].fn(answer="screwed")
    out = t["nam_pick"].fn(key="V-2", quantity=4)
    assert "In the cart for 'valve': V-2" in out and "Cart: 1 of 2 chosen item(s)" in out
    assert "Next item: 'thermowell'" in out and "| T-1 | material |" in out
    out = t["nam_pick"].fn(key="T-1")
    assert "The quantity is still to come" in out and "Every chosen item is in the cart" in out
    out = t["nam_pick"].fn(item="valve", remove=True)
    assert out.startswith("Took 'valve' out of the cart")
    assert case.current_item(_data(t))["name"] == "valve"


# -- 1j: the matching PURs ------------------------------------------------------------

def _cart(t, chosen=("valve", "thermowell")):
    _need(t)
    t["nam_choose"].fn(items=list(chosen))
    if "valve" in chosen:
        t["nam_answer"].fn(item="valve", answer="screwed")
        t["nam_pick"].fn(item="valve", key="V-2", quantity=4)
    if "thermowell" in chosen:
        t["nam_pick"].fn(item="thermowell", key="T-1", quantity=2)


def test_the_pur_holding_every_material_even_one_not_chosen_is_the_100_match(t):
    _cart(t)
    out = t["nam_tenders"].fn()
    assert "A PUR holds all 3: 100%." in out
    rows = [r for r in out.splitlines() if r.startswith("| ") and "PUR-" in r]
    assert rows[0].startswith("| 100% | PUR-B | 3 of 3 materials |")
    assert "valve: V-2" in rows[0] and "4500000003" in rows[0]
    assert "| 33% | PUR-C | 1 of 3 materials |" in out
    assert _data(t)["matched"][0] == {"pur": "PUR-B", "match": 100, "covers": "3 of 3 materials"}


def test_when_no_pur_holds_all_the_one_holding_most_is_100(t):
    pool = [{"name": n, "picked": None, "records": narrow._sap(SAP[n])}
            for n in ("gasket", "valve", "bolt")]
    m = narrow.coverage(pool)
    assert not m["all"] and m["most"] == 2
    assert [(p["pur"], p["match"]) for p in m["purs"][:2]] == [("PUR-B", 100), ("PUR-A", 100)]
    assert next(p for p in m["purs"] if p["pur"] == "PUR-D")["match"] == 50


# -- stage 3: one PR per cart item ----------------------------------------------------

def test_each_cart_item_gets_its_own_pr_and_the_officers_fields_carry_over(t):
    _cart(t)
    t["nam_pr"].fn(item="valve", action="set", delivery_date="2026-12-31", plant="1100",
                   storage_location="S001", justification="Line 4 overhaul")
    out = t["nam_pr"].fn(item="valve", action="confirm")
    assert "CONFIRMED" in out and "PRs still to do: thermowell" in out
    out = t["nam_pr"].fn(item="thermowell", action="fill")
    assert "| Plant | 1100 (as for 'valve') |" in out and "PR for 'thermowell' (draft)" in out
    out = t["nam_pr"].fn(item="thermowell", action="confirm")
    assert "Every chosen item has its PR" in out
    from waku.nam import flow
    assert flow.stage_of(_data(t)) == ("3b", "done")


def test_a_flagged_price_waits_for_the_officers_decision(t):
    _cart(t, ("thermowell",))
    data = _data(t)
    it = case.item(data, "thermowell")
    from waku.nam import pr
    p = pr.fill(data, it)
    p["price"].update(flag=True, result="AHR")
    assert "a decision on the price, flagged AHR" in "; ".join(pr.missing(p))
    pr.set_price(p, accept=True)
    assert not any("decision" in m for m in pr.missing(p))
    with pytest.raises(ValueError, match="no flag to accept"):
        pr.set_price(p, accept=True)


# -- undo ----------------------------------------------------------------------------

def test_undo_goes_back_one_officer_act_at_a_time(t):
    _cart(t)
    out = t["nam_undo"].fn()
    assert out.startswith("Took back: put T-1 in the cart for 'thermowell'")
    out = t["nam_undo"].fn()
    assert out.startswith("Took back: put V-2 in the cart for 'valve'")
    out = t["nam_undo"].fn()
    assert out.startswith("Took back: the answer 'screwed'")
    assert len(case.remaining(case.item(_data(t), "valve"))) == 3
    out = t["nam_undo"].fn()
    assert out.startswith("Took back: chose valve, thermowell")
    assert not any("selected" in i for i in _data(t)["items"])
    out = t["nam_undo"].fn()
    assert out.startswith("Took back: set the need")
    assert "nothing to take back" in t["nam_undo"].fn()


def test_undo_after_a_new_act_takes_back_that_act_first(t):
    _cart(t)
    t["nam_undo"].fn()                                   # T-1 out
    t["nam_pick"].fn(item="thermowell", key="T-2", quantity=1)
    out = t["nam_undo"].fn()
    assert out.startswith("Took back: put T-2 in the cart")
    out = t["nam_undo"].fn(steps=2)
    assert out.startswith("Took back: put V-2 in the cart for 'valve'; the answer 'screwed'")


def test_undo_brings_the_question_back_and_the_word_undo_works_too(t):
    _need(t)
    _choose_q(t)
    t["nam_choose"].fn(items=["valve"])
    out = t["nam_answer"].fn(answer="undo")
    assert "The question of which materials go forward is open again." in out
    assert stage_tools.reminder(t["_conn"], "chat-c")[1]["options"][-1] == "All of them"


def test_a_confirmed_pr_is_never_taken_back(t):
    _cart(t, ("thermowell",))
    t["nam_pr"].fn(action="set", delivery_date="2026-12-31", plant="1100",
                   storage_location="S001", justification="Line 4")
    t["nam_pr"].fn(action="confirm")
    out = t["nam_undo"].fn()
    assert out.startswith("REFUSED: that would take back the confirmed PR of thermowell")
    assert "has a confirmed PR" in t["nam_pick"].fn(item="thermowell", remove=True)

