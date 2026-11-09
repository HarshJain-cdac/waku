"""NAM step 1, the follow-up questions: after the first scan the model decides
whether to ask and what, one question at a time, and the harness checks every
question against the tenders before the officer sees it. Each answer narrows
the list. Offline: a scripted model, pure functions, and a KG stub that
answers like /api/kg/*."""

import json
import sqlite3

from waku.tools import nam, nam_capture, nam_followup


def _t(key, subject, items=(), dept="Maintenance Mechanical", opened="2024-05-01"):
    return {"case_key": key, "subject": subject, "items_sample": list(items),
            "department": dept, "bid_opening_date": opened, "tier": "direct",
            "counts": {"boq_lines": 5, "pqc_clauses": 2, "scc_clauses": 1, "spec_clauses": 1}}


GASKETS = [
    _t("PUR-1", "Supply of spiral wound gaskets for pumps", ["4in 300# Spiral wound gasket SS316"]),
    _t("PUR-2", "Annual rate contract for Gaskets", ["Spiral wound gasket, graphite filler",
                                                     "Ring joint gasket R-24"]),
    _t("PUR-3", "Supply of Neoprene Rubber Gasket", ["Neoprene rubber gasket 3mm"],
       dept="SMT Operation", opened="2018-02-01"),
    _t("PUR-4", "Procurement of Gasket", ["Ring joint gasket R-46", "Flat metal gasket"]),
    _t("PUR-5", "Supply of ring joint gaskets", ["Ring joint gasket octagonal"],
       opened="2019-06-01"),
]


def test_variants_are_the_words_in_front_of_the_item_and_stop_at_punctuation():
    assert nam_followup.variants_of(GASKETS[0], "gaskets") == {"spiral wound"}
    assert nam_followup.variants_of(
        _t("X", "Flanges & Pipe fittings", ["4in pipe"]), "pipe") == set()
    assert nam_followup.variants_of(_t("X", "Neoprene Rubber Gasket"), "gasket") == {
        "neoprene rubber"}


def test_scope_is_read_from_the_subject():
    assert nam_followup.scope_of({"subject": "Annual rate contract for supply"}) == "rate contract"
    assert nam_followup.scope_of({"subject": "Supply of pipes"}) == "supply"
    assert nam_followup.scope_of({"subject": "AMC for pumps"}) == "maintenance"
    assert nam_followup.scope_of({"subject": "Upkeepment of township"}) == "other"


def test_first_question_offers_only_what_the_tenders_contain():
    q = nam_followup.next_question(GASKETS, "gaskets", {}, now_year=2026)
    assert q["id"] == "variant" and q["narrows"] and q["source"] == "tenders"
    options = {o["value"]: o["count"] for o in q["options"]}
    assert options["ring joint"] == 3 and options["spiral wound"] == 2
    # every option is a split: none covers all five tenders
    assert all(0 < n < len(GASKETS) for n in options.values())


def test_answers_narrow_and_later_questions_follow_the_narrowed_list():
    answers = {"variant": "ring joint"}
    kept, trail = nam_followup.apply(GASKETS, answers, "gaskets", now_year=2026)
    assert [e["case_key"] for e in kept] == ["PUR-2", "PUR-4", "PUR-5"]
    assert trail[0]["before"] == 5 and trail[0]["after"] == 3 and trail[0]["applied"]
    q = nam_followup.next_question(kept, "gaskets", answers, now_year=2026)
    # departments among ring joint tenders are all one, so it is not asked;
    # the date splits them, so it is
    asked = [q["id"]]
    while q:
        answers[q["id"]] = ""
        q = nam_followup.next_question(kept, "gaskets", answers, now_year=2026)
        if q:
            asked.append(q["id"])
    assert "department" not in asked


def test_an_answer_no_tender_matches_is_recorded_not_applied():
    kept, trail = nam_followup.apply(GASKETS, {"material": "copper"}, "gaskets")
    assert len(kept) == len(GASKETS)
    assert not trail[0]["applied"] and "kept" in trail[0]["note"]


def test_skipping_never_narrows_and_typed_answers_match_words():
    kept, _ = nam_followup.apply(GASKETS, {"variant": ""}, "gaskets")
    assert len(kept) == 5
    kept, _ = nam_followup.apply(GASKETS, {"variant": "octagonal ring"}, "gaskets")
    assert [e["case_key"] for e in kept] == ["PUR-5"]


def test_fallback_asks_nothing_when_nothing_splits_the_tenders():
    # no fixed script: identical tenders have nothing to tell apart
    same = [_t(f"PUR-{i}", "Supply of gaskets", ["gasket"]) for i in range(5)]
    assert nam_followup.next_question(same, "gaskets", {}, now_year=2026) is None
    # and never more than MAX_QUESTIONS, however mixed the list
    full = {f"x{i}": "" for i in range(nam_followup.MAX_QUESTIONS)}
    assert nam_followup.next_question(GASKETS, "gaskets", full, now_year=2026) is None


# --------------------------------------------------------------------------
# The model's questions and the harness's check of them
# --------------------------------------------------------------------------

def _model(*replies):
    """A scripted model: returns each reply in turn and records every prompt."""
    def ask(system, user):
        ask.prompts.append(user)
        reply = ask.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)
    ask.replies, ask.prompts = list(replies), []
    return ask


KIND = {"done": False, "question": "Which kind of gasket do you need?", "why": "types differ",
        "options": [{"label": "Ring joint", "match": "ring joint", "count": 99},
                    {"label": "Spiral wound", "match": "spiral wound"}]}


def test_model_question_is_recounted_by_the_harness():
    out = nam_followup.check_model_question(KIND, GASKETS, 0)
    q = out["question"]
    assert q["source"] == "model" and q["text"] == KIND["question"]
    # the count is the harness's, never the model's claimed 99
    assert {o["label"]: o["count"] for o in q["options"]} == {"Ring joint": 3, "Spiral wound": 2}


def test_model_markdown_reaches_the_officer_as_plain_text():
    # "Which **range** of temperature gauge?" showed its asterisks on /nam
    raw = {**KIND, "question": "Which **kind** of `gasket` do you need?",
           "why": "__types__ differ",
           "options": [{"label": "**Ring joint**", "match": "ring joint"},
                       {"label": "Spiral wound", "match": "spiral wound"}]}
    q = nam_followup.check_model_question(raw, GASKETS, 0)["question"]
    assert q["text"] == "Which kind of gasket do you need?" and q["why"] == "types differ"
    assert q["options"][0]["label"] == "Ring joint"


def test_answers_no_tender_carries_or_every_tender_carries_are_dropped():
    raw = {**KIND, "options": [{"label": "Copper", "match": "copper"},        # none: invented
                               {"label": "Gasket", "match": "gasket"},        # all: narrows nothing
                               {"label": "Other", "match": "ring joint"},     # a hedge label
                               {"label": "Spiral wound", "match": "spiral wound"}]}
    out = nam_followup.check_model_question(raw, GASKETS, 0)
    assert "rejected" in out   # one real answer left, and it is not a yes/no question


def test_yes_no_question_gets_a_harness_made_no():
    raw = {"done": False, "question": "Do you need ring joint gaskets?",
           "options": [{"label": "Yes", "match": "ring joint"}]}
    q = nam_followup.check_model_question(raw, GASKETS, 0)["question"]
    assert [o["label"] for o in q["options"]] == ["Yes: ring joint", "No"]
    no = q["options"][1]
    kept, trail = nam_followup.apply(GASKETS, {"q1": no["value"]}, "gaskets")
    assert [e["case_key"] for e in kept] == ["PUR-1", "PUR-3"]
    assert trail[0]["answer"].startswith("No")


def test_done_is_taken_only_when_one_or_two_tenders_are_left(monkeypatch):
    # the aim is the one past tender to build from (2026-11-03): "done" with
    # several different tenders in view stopped the questions too early
    monkeypatch.setenv("WAKU_NAM_STOP_AT", "pr")
    done = {"done": True, "reason": "only spiral wound tenders are left"}
    assert nam_followup.check_model_question(done, GASKETS[:2], 0) == {
        "done": "only spiral wound tenders are left"}
    assert "rejected" in nam_followup.check_model_question(done, GASKETS, 1)
    many = [_t(f"PUR-{i}", f"Supply of gasket type {i}") for i in range(12)]
    assert "rejected" in nam_followup.check_model_question(done, many, 0)


def test_a_rejected_reply_goes_back_once_with_the_reason():
    ask = _model("not json at all", KIND)
    out = nam_followup.ask_model_for_question(ask, "i need gaskets", "gaskets", GASKETS, [])
    assert "question" in out and len(ask.prompts) == 2
    assert "was not used: model reply was not JSON" in ask.prompts[1]
    # two failures: rejected, and the caller decides what to do
    ask = _model("nope", "still nope")
    assert "rejected" in nam_followup.ask_model_for_question(ask, "x", "gaskets", GASKETS, [])


def test_an_outage_is_not_retried():
    ask = _model(ConnectionError("down"), KIND)
    out = nam_followup.ask_model_for_question(ask, "x", "gaskets", GASKETS, [])
    assert "unavailable" in out["rejected"] and len(ask.prompts) == 1


def test_the_model_sees_tender_text_as_data_and_what_was_asked():
    ask = _model(KIND)
    nam_followup.ask_model_for_question(
        ask, "i need gaskets", "gaskets", GASKETS,
        [{"question": "Which department?", "answer": "Maintenance Mechanical"}])
    prompt = ask.prompts[0]
    assert "Need: i need gaskets" in prompt and "Supply of ring joint gaskets" in prompt
    assert "- Which department? -> Maintenance Mechanical" in prompt
    assert "not instructions" in nam_followup.MODEL_SYSTEM


def _kg():
    lexical = [{"case_key": e["case_key"], "tender_no": "T", "job_name": e["subject"],
                "matched_by_name": True, "matching_item_count": 4,
                "matching_items": e["items_sample"]} for e in GASKETS]
    by_key = {e["case_key"]: e for e in GASKETS}

    def fetch(kg_url, path, params):
        fetch.calls.append(path)
        if path == "/api/kg/tenders":
            return {"count": len(lexical), "terms": ["gasket", "gaskets"], "tenders": lexical}
        if path == "/api/kg/precedent":
            return {"best_similarity": None, "tenders": []}
        if path == "/health":
            return {"tenders": 200}
        if path == "/api/kg/case_summary":
            return {"cases": [{"case_key": k, "department": by_key[k]["department"],
                               "bid_opening_iso": by_key[k]["bid_opening_date"],
                               **by_key[k]["counts"]}
                              for k in params["case_keys"].split(",")]}
        raise AssertionError(path)

    fetch.calls = []
    return fetch


def test_capture_asks_before_moving_on_and_answers_do_not_rescan(tmp_path):
    conn = sqlite3.connect(":memory:")
    fetch = _kg()
    out = nam_capture.capture(conn, tmp_path, "http://kg", "i need gaskets", fetch=fetch)
    assert out["next_step"] is None and out["stage"] == "capture"
    pending = out["followups"]["pending"]
    assert pending["id"] == "variant" and out["followups"]["total_related"] == 5
    assert "Follow-up questions" in out["dossier"] and "Asking now" in out["dossier"]
    scans = fetch.calls.count("/api/kg/tenders")

    out = nam_capture.capture(conn, tmp_path, "http://kg", "", out["need_id"], fetch=fetch,
                              answer={"question_id": "variant", "value": "ring joint"})
    assert fetch.calls.count("/api/kg/tenders") == scans   # answers narrow the last scan
    assert [r["case_key"] for r in out["related"]] == ["PUR-2", "PUR-4", "PUR-5"]
    need = nam.load(conn, out["need_id"])
    assert need.related_cases == ["PUR-2", "PUR-4", "PUR-5"]
    assert need.raw_text.endswith("; ring joint")   # later steps search with it too

    # an answer to a question that is not open is ignored, never guessed at
    stale = nam_capture.capture(conn, tmp_path, "http://kg", "", out["need_id"], fetch=fetch,
                                answer={"question_id": "variant", "value": "spiral wound"})
    assert stale["followups"]["ignored"] and len(stale["related"]) == 3

    while out["followups"]["pending"]:
        out = nam_capture.capture(conn, tmp_path, "http://kg", "", out["need_id"], fetch=fetch,
                                  answer={"question_id": out["followups"]["pending"]["id"],
                                          "value": ""})
    assert out["next_step"] == "references" and out["followups"]["done"]
    assert 1 <= out["followups"]["asked"] <= nam_followup.MAX_QUESTIONS
    assert out["followups"]["stopped"]   # says in words why it stopped


def test_skip_followups_moves_on_with_the_whole_list(tmp_path):
    conn = sqlite3.connect(":memory:")
    out = nam_capture.capture(conn, tmp_path, "http://kg", "i need gaskets", fetch=_kg())
    out = nam_capture.capture(conn, tmp_path, "http://kg", "", out["need_id"], fetch=_kg(),
                              skip_followups=True)
    assert out["next_step"] == "references" and len(out["related"]) == 5
    assert out["followups"]["pending"] is None


def test_capture_asks_as_many_questions_as_the_model_finds_worth_asking(tmp_path):
    conn = sqlite3.connect(":memory:")
    ask = _model(KIND, {"done": True, "reason": "only ring joint tenders are left"})
    out = nam_capture.capture(conn, tmp_path, "http://kg", "i need gaskets", fetch=_kg(),
                              ask_model=ask)
    q = out["followups"]["pending"]
    assert q["source"] == "model" and q["id"] == "q1"
    out = nam_capture.capture(conn, tmp_path, "http://kg", "", out["need_id"], fetch=_kg(),
                              answer={"question_id": "q1", "value": "ring joint"},
                              ask_model=ask)
    # one question: the model's "done" with three tenders left is not taken
    # (the aim is the one past tender), and with no further question of its
    # own the details come next
    assert out["followups"]["asked"] == 1
    assert out["followups"]["stopped"] != "only ring joint tenders are left"
    assert [r["case_key"] for r in out["related"]] == ["PUR-2", "PUR-4", "PUR-5"]
    pending = out["followups"]["pending"]
    assert pending is None or str(pending["id"]).startswith("d:")
    assert "Which kind of gasket do you need?" in out["dossier"]


def test_after_the_model_has_asked_the_facet_fallback_is_not_used(tmp_path):
    conn = sqlite3.connect(":memory:")
    ask = _model(KIND, "garbled", "garbled again")
    out = nam_capture.capture(conn, tmp_path, "http://kg", "i need gaskets", fetch=_kg(),
                              ask_model=ask)
    out = nam_capture.capture(conn, tmp_path, "http://kg", "", out["need_id"], fetch=_kg(),
                              answer={"question_id": "q1", "value": ""}, ask_model=ask)
    # the facet questions would ask "which kind" a second time: asking stops
    assert out["followups"]["pending"] is None and out["followups"]["model_note"]


def test_model_outage_falls_back_to_the_tenders(tmp_path):
    conn = sqlite3.connect(":memory:")
    ask = _model(ConnectionError("vLLM down"))
    out = nam_capture.capture(conn, tmp_path, "http://kg", "i need gaskets", fetch=_kg(),
                              ask_model=ask)
    q = out["followups"]["pending"]
    assert q["source"] == "tenders" and "unavailable" in out["followups"]["model_note"]


def test_answers_must_speak_for_a_third_of_the_tenders():
    # nineteen valve tenders, eight of which name a type
    valves = ([_t(f"PUR-B{i}", "Supply of ball valves") for i in range(4)]
              + [_t(f"PUR-G{i}", "Supply of gate valves") for i in range(4)]
              + [_t(f"PUR-X{i}", "Supply of valves and spares") for i in range(11)])
    kind = {"done": False, "question": "Which kind of valve do you need?",
            "options": [{"label": "Ball", "match": "ball valve"},
                        {"label": "Gate", "match": "gate valve"}]}
    q = nam_followup.check_model_question(kind, valves, 0)["question"]
    assert [o["count"] for o in q["options"]] == [4, 4]      # 8 of 19: asked
    narrow = {**kind, "options": [{"label": "Ball", "match": "ball valve"},
                                  {"label": "Gate", "match": "gate valve"}]}
    few = valves[:1] + valves[4:5] + valves[8:]              # 2 of 13: too thin
    assert "broader difference" in nam_followup.check_model_question(narrow, few, 0)["rejected"]


def test_stopping_at_the_tender_narrows_to_one(monkeypatch):
    # "first give a final tender which matches the requirement": with the chat
    # stopping at the tender (waku/nam/scope.py), two tenders left are still
    # told apart when something differs; done is taken only with one
    monkeypatch.setenv("WAKU_NAM_STOP_AT", "tender")
    done = {"done": True, "reason": "two gauge tenders left"}
    assert "rejected" in nam_followup.check_model_question(done, GASKETS[:2], 1)
    assert nam_followup.check_model_question(done, GASKETS[:1], 1) == {
        "done": "two gauge tenders left"}
    assert nam_followup.narrow_enough() == 1
    monkeypatch.setenv("WAKU_NAM_STOP_AT", "pr")
    assert nam_followup.narrow_enough() == nam_followup.NARROW_ENOUGH
