"""DETERMINISTIC EVAL — the Need Assessment Module.

NAM's job is to classify a stated need, find the past tenders that actually
match it, and let the OFFICER choose. The FRS is explicit about that last part:
downstream documents are built "based on the tender(s) selected by the user,
rather than by AI selection alone". These tests pin the classification, the
honesty of the numbers on a card, and the selection gate.

Offline: classification and scoring are pure functions; retrieval is not
exercised here (it needs the graph).
"""

from __future__ import annotations

import sqlite3

import pytest

from waku.tools import nam


@pytest.fixture
def conn():
    return sqlite3.connect(":memory:")


# --- classification --------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("AMC for housekeeping at Plant-1", nam.SERVICES),
    ("Manpower — 14 skilled positions", nam.SERVICES),
    ("11kV VCB panels for Substation-3", nam.GOODS),
    ("supply of gaskets for RTA", nam.GOODS),
    ("Painting work — Plant 2", nam.WORKS),
    ("civil work for the new block", nam.WORKS),
])
def test_category_is_predicted_from_free_text(text, expected):
    assert nam.classify(text)["category"]["value"] == expected


def test_a_prediction_carries_the_words_that_made_it():
    """An officer can only judge a prediction if they can see why it was made."""
    pred = nam.classify("AMC for housekeeping at Plant-1")["category"]
    assert pred["basis"] == "amc"


def test_tender_type_is_never_claimed_confidently():
    """Open vs Limited vs OEM turns on value thresholds and OEM status, not on
    a word in a sentence. A keyword is a suggestion; it must still be asked."""
    pred = nam.classify("limited tender for gaskets")["tender_type"]
    assert pred["value"] == "Limited"
    assert pred["confident"] is False


def test_only_undecided_fields_are_asked_about(conn):
    """FRS 3.1.2: ask a follow-up 'only for whichever field it could not
    confidently predict'."""
    need = nam.create(conn, "AMC for housekeeping at Plant-1 for 12 months")
    assert need.unresolved == ["tender_type"]
    assert need.category["value"] == nam.SERVICES
    assert need.procurement_type["value"] == "OPEX"


def test_location_term_and_quantity_are_captured_separately(conn):
    need = nam.create(conn, "supply of 500 nos gate valves for Plant 2")
    assert need.quantity == "500 nos"
    assert need.location.lower().startswith("plant")


# --- the search query ------------------------------------------------------

def test_the_search_drops_location_and_term(conn):
    """Searching the whole sentence looks for tenders whose subject says
    "plant" and "months" — which is every tender, and therefore no tender."""
    need = nam.create(conn, "AMC for housekeeping at Plant-1 for 12 months")
    query = nam.search_query(need).lower()
    assert "housekeeping" in query
    assert "plant" not in query and "month" not in query


# --- what a card is allowed to claim ---------------------------------------

def test_match_strength_is_explainable():
    """Every percentage a card shows must come with what it means. A cosine
    distance cannot be explained to a procurement officer; this can."""
    score, basis = nam.match_strength(
        "gaskets", {"matching_item_count": 30},
        {"job_name": "Procurement of Gasket"})
    assert score > 0
    assert "gasket" in basis.lower()


def test_singular_and_plural_count_as_matching():
    """"gaskets" against "Procurement of Gasket" scored zero coverage before
    this — the one tender whose entire subject IS the requirement."""
    with_s, _ = nam.match_strength("gaskets", {"matching_item_count": 30},
                                   {"job_name": "Procurement of Gasket"})
    without_s, _ = nam.match_strength("gasket", {"matching_item_count": 30},
                                      {"job_name": "Procurement of Gaskets"})
    assert with_s == without_s > 50


def test_a_tender_that_merely_mentions_the_thing_scores_lower():
    """Buying it and mentioning it are different, and the card must say so."""
    bought, _ = nam.match_strength("gaskets", {"matching_item_count": 40},
                                   {"job_name": "ARC for gaskets"})
    mentioned, _ = nam.match_strength("gaskets", {"matching_item_count": 1},
                                      {"job_name": "Spare supply for pumps"})
    assert bought > mentioned


def test_no_terms_means_no_score():
    score, basis = nam.match_strength("for the of", {}, {"job_name": "anything"})
    assert score == 0 and "nothing substantive" in basis


# --- the gate --------------------------------------------------------------

def test_nothing_is_selected_until_the_officer_selects(conn):
    """The FRS gate. A fresh need has chosen no precedent, and generation
    downstream reads only what the officer picked."""
    need = nam.create(conn, "AMC for housekeeping at Plant-1")
    assert need.selected_cases == []
    assert need.stage == "describe"


def test_a_need_gets_a_unique_file_number(conn):
    first = nam.create(conn, "AMC for housekeeping")
    second = nam.create(conn, "supply of gaskets")
    assert first.need_id != second.need_id
    assert first.need_id.startswith("NAM-")


def test_a_need_round_trips(conn):
    need = nam.create(conn, "supply of gaskets")
    need.selected_cases = ["PUR-MECHMNT-1008357"]
    nam.save(conn, need)
    again = nam.load(conn, need.need_id)
    assert again is not None
    assert again.selected_cases == ["PUR-MECHMNT-1008357"]


def test_the_vocabularies_match_the_frs():
    assert set(nam.CATEGORIES) == {nam.GOODS, nam.SERVICES, nam.WORKS}
    assert "Emergency" in nam.PROCUREMENT_TYPES and "CAPEX" in nam.PROCUREMENT_TYPES
    assert {"Open", "Limited", "OEM", "Proprietary", "GeM"} <= set(nam.TENDER_TYPES)
    # the sub-types the UI's three category cards offer
    assert "Codified" in nam.SUBTYPES[nam.GOODS]
    assert "Consultancy" in nam.SUBTYPES[nam.SERVICES]
    assert "Within impanelment" in nam.SUBTYPES[nam.WORKS]


# --- the selection gate, as code rather than instruction ---------------------

def test_no_selection_yields_no_material(conn):
    """The FRS rule made structural: with nothing selected there is nothing to
    build from, whatever the matching step scored."""
    need = nam.create(conn, "AMC for housekeeping chemicals")
    material = nam.selected_material(need, "http://127.0.0.1:1")
    assert material["selected"] == []
    assert material["pqc"] == [] and material["boq"] == []
    assert "No tender selected" in material["note"]


def test_material_is_read_only_from_selected_cases(conn, monkeypatch):
    """A case the officer did not pick contributes nothing, however well it
    scored. Proven by giving the fetcher two tenders and selecting one."""
    need = nam.create(conn, "AMC for housekeeping chemicals")
    need.selected_cases = ["PUR-CHOSEN-1"]

    def fake_case(case_key, kg_url):
        return {
            "case_key": case_key, "tender_no": f"TND-{case_key}",
            "job_name": "Housekeeping chemicals",
            "pqc": [{"text": f"A qualifying criterion belonging to {case_key}, "
                             f"long enough to survive the minimum length filter."}],
            "scc": [], "tech_spec": [],
            "boq": [{"item": f"item from {case_key}"}],
            "counts": {},
        }

    monkeypatch.setattr(nam, "case_detail", fake_case)
    material = nam.selected_material(need, "http://x")
    assert material["counts"]["pqc"] == 1
    assert "PUR-CHOSEN-1" in material["pqc"][0]["text"]
    assert all(c["case_key"] == "PUR-CHOSEN-1" for c in material["pqc"])


def test_every_merged_clause_carries_its_tender(conn, monkeypatch):
    """Merged material without attribution is how a clause from one tender ends
    up cited to another."""
    need = nam.create(conn, "gaskets")
    need.selected_cases = ["A", "B"]

    def fake_case(case_key, kg_url):
        return {"case_key": case_key, "tender_no": f"TND-{case_key}",
                "job_name": f"subject {case_key}",
                "pqc": [{"text": f"Clause unique to {case_key}. " + "x" * 60}],
                "scc": [], "tech_spec": [], "boq": [], "counts": {}}

    monkeypatch.setattr(nam, "case_detail", fake_case)
    material = nam.selected_material(need, "http://x")
    assert len(material["pqc"]) == 2
    for clause in material["pqc"]:
        assert clause["case_key"] and clause["tender_no"]


def test_duplicate_clauses_across_selected_tenders_collapse(conn, monkeypatch):
    """Selecting two similar tenders must not print the same criterion twice
    under two tender numbers."""
    need = nam.create(conn, "gaskets")
    need.selected_cases = ["A", "B"]
    same = "The bidder shall be a manufacturer or authorised dealer of the offered item."

    def fake_case(case_key, kg_url):
        return {"case_key": case_key, "tender_no": f"TND-{case_key}",
                "job_name": "x", "pqc": [{"text": same}], "scc": [],
                "tech_spec": [], "boq": [], "counts": {}}

    monkeypatch.setattr(nam, "case_detail", fake_case)
    assert len(nam.selected_material(need, "http://x")["pqc"]) == 1


def test_category_carries_a_stable_id():
    """The UI switches on "goods"/"services"/"works"; a label is a display
    decision and will change."""
    pred = nam.classify("AMC for housekeeping")["category"]
    assert pred["id"] == "services"
    assert nam.category_label("works") == nam.WORKS
    assert set(nam.CATEGORY_ID.values()) == {"goods", "services", "works"}


# --- the capture screen actually has something to render --------------------
# "Waiting on the conversation engine" was the empty state the officer saw:
# the UI held the conversation in localStorage and never called the backend.

def test_the_classifier_answers_every_capture_turn(conn):
    """Whatever the officer types, capture must produce something to say — a
    reading of the requirement, or a question about what it could not decide.
    A turn that yields neither is the blank screen this replaced."""
    for text in ("AMC for housekeeping at Plant-1 for 12 months",
                 "11kV VCB panels for Substation-3",
                 "something completely unclassifiable"):
        need = nam.create(conn, text)
        has_reading = any(getattr(need, f)["value"]
                          for f in ("category", "procurement_type", "tender_type"))
        has_question = bool(need.unresolved)
        assert has_reading or has_question, f"nothing to say about {text!r}"


def test_an_officer_answer_settles_the_open_field(conn):
    """The capture loop ends when nothing is left to ask — that is what turns
    on the 'look for similar past tenders' step."""
    need = nam.create(conn, "AMC for housekeeping at Plant-1")
    assert need.unresolved == ["tender_type"]
    need.tender_type = {"value": "Open", "basis": "you set this", "confident": True}
    nam.save(conn, need)
    assert nam.load(conn, need.need_id).unresolved == []


def test_the_frontend_vocabularies_match_the_backend():
    """The capture screen matches a free-text answer against these lists before
    storing it, so a drift here stores prose where a vocabulary value belongs."""
    from pathlib import Path

    steps = (Path(__file__).resolve().parents[2]
             / "nit-forge-ui" / "src" / "lib" / "nam-steps.ts")
    if not steps.exists():
        import pytest

        pytest.skip("frontend not checked out")
    source = steps.read_text(encoding="utf-8")
    for value in nam.TENDER_TYPES:
        assert f'"{value}"' in source, f"tender type {value} missing from the UI vocabulary"
    for value in nam.PROCUREMENT_TYPES:
        assert f'"{value}"' in source, f"procurement type {value} missing from the UI vocabulary"


# --- tender type is a tendering phrase, never a stray word -------------------

@pytest.mark.parametrize("text", [
    "ARC for gaskets 2024-26 in Numaligarh Refinery limited",
    "Supply of valves to Numaligarh Refinery Limited",
    "open area painting at Plant 2",
    "spot welding of pipe supports",
])
def test_a_company_name_or_ordinary_word_is_not_a_tender_type(text):
    """NRL's legal name ends in "Limited" and sits in a large share of subjects.
    A bare-word rule typed nearly every one of them a Limited Tender."""
    assert nam.classify(text)["tender_type"]["value"] is None


@pytest.mark.parametrize("text,expected", [
    ("limited tender for gaskets", "Limited"),
    ("open tender for housekeeping", "Open"),
    ("procure on GeM", "GeM"),
    ("OEM supply of spares", "OEM"),
    ("single-source procurement of relays", "Proprietary"),
])
def test_a_real_tendering_phrase_is_still_read(text, expected):
    assert nam.classify(text)["tender_type"]["value"] == expected


def test_a_suggested_tender_type_is_still_asked_about(conn):
    """Confidence, not presence. A keyword suggestion has a value but must still
    be confirmed by the officer."""
    need = nam.create(conn, "open tender for housekeeping AMC")
    assert need.tender_type["value"] == "Open"
    assert "tender_type" in need.unresolved


# --- replicate from a reference ----------------------------------------------

def test_a_sap_shaped_number_is_answered_not_searched():
    """PR and PO numbers live in SAP, which is not connected. Saying so beats a
    generic 'not found' that sends the officer looking for a typo."""
    result = nam.lookup_reference("0010002456", "http://127.0.0.1:1")
    assert result["kind"] == "sap"
    assert "SAP" in result["note"]


def test_an_empty_reference_asks_for_one():
    assert nam.lookup_reference("", "http://x")["kind"] == "unknown"


def test_an_ambiguous_reference_is_not_opened(monkeypatch):
    """Two tenders sharing a base number are shown for the officer to choose.
    Opening one for them is AI selection by the back door."""
    monkeypatch.setattr(nam, "_get", lambda *a, **k: {
        "tier": "core", "ambiguous": True,
        "matches": [{"case_key": "PUR-A-1"}, {"case_key": "PUR-B-2"}]})
    opened: list = []
    monkeypatch.setattr(nam, "case_detail", lambda k, u: opened.append(k) or {})
    result = nam.lookup_reference("OC01000435", "http://kg")
    assert result["ambiguous"] and result["record"] is None
    assert opened == []


def test_replicating_a_named_tender_selects_it(conn, monkeypatch):
    """The officer typed this tender and asked to replicate it — an explicit
    human choice, which is exactly what the FRS gate asks for."""
    monkeypatch.setattr(nam, "case_detail", lambda k, u: {
        "case_key": k, "job_name": "ARC for gaskets 2024-26"})
    need = nam.replicate(conn, "PUR-MECHMNT-1008357", "http://kg")
    assert need is not None
    assert need.selected_cases == ["PUR-MECHMNT-1008357"]
    assert need.stage == "selected"
    assert need.category["value"] == nam.GOODS


def test_replicating_an_unreadable_tender_creates_nothing(conn, monkeypatch):
    monkeypatch.setattr(nam, "case_detail", lambda k, u: {"error": "unreachable"})
    assert nam.replicate(conn, "PUR-X-1", "http://kg") is None


# --- the officer's answers are checked before they are stored ----------------

def test_a_category_id_or_label_is_accepted(conn):
    need = nam.create(conn, "painting of tank farm structures")
    assert nam.apply_update(need, {"category": "works"}) is None
    assert need.category["value"] == nam.WORKS and need.category["id"] == "works"
    assert nam.apply_update(need, {"category": nam.GOODS}) is None
    assert need.category["id"] == "goods"


def test_an_unknown_category_is_refused(conn):
    need = nam.create(conn, "painting")
    assert nam.apply_update(need, {"category": "furniture"}) is not None


def test_switching_path_clears_a_subtype_that_no_longer_fits(conn):
    """Works -> Goods kept "Repetitive", describing a case that cannot exist."""
    need = nam.create(conn, "painting")
    nam.apply_update(need, {"category": "works", "subtype": "Repetitive"})
    assert need.subtype["value"] == "Repetitive"
    nam.apply_update(need, {"category": "goods"})
    assert need.subtype["value"] is None


def test_a_subtype_is_judged_against_its_own_path(conn):
    """'Consultancy' is valid — for Services. On a Goods case it is refused."""
    need = nam.create(conn, "painting")
    nam.apply_update(need, {"category": "goods"})
    assert nam.apply_update(need, {"subtype": "Consultancy"}) is not None
    assert nam.apply_update(need, {"subtype": "Codified"}) is None


def test_a_subtype_sent_with_a_category_uses_the_new_path(conn):
    need = nam.create(conn, "painting")
    nam.apply_update(need, {"category": "goods"})
    assert nam.apply_update(need, {"category": "works", "subtype": "Repetitive"}) is None
    assert need.subtype["value"] == "Repetitive"


def test_prose_is_never_stored_as_a_tender_type(conn):
    need = nam.create(conn, "painting")
    assert nam.apply_update(need, {"tender_type": "yes please, the usual"}) is not None
    assert need.tender_type["value"] is None
    assert nam.apply_update(need, {"tender_type": "Open"}) is None
    assert need.tender_type["confident"] is True


@pytest.mark.parametrize("text,expected", [
    ("about 34 positions", "34 positions"),
    ("12 sets of spares", "12 sets"),
    ("500 nos gate valves", "500 nos"),
    ("20 persons for housekeeping", "20 persons"),
])
def test_quantities_are_read_in_the_plural(text, expected):
    """Officers write "34 positions", not "34 position". The singular-only
    pattern dropped exactly the quantities a manpower case turns on."""
    assert nam.classify(text)["quantity"] == expected
