"""Stage 1, steps 1d to 1j: the records that match an item, narrowed to one.

  find()      1d: SAP's PR, PO and service lines (sap_search) for the item,
              by meaning and by keyword. Each record is one candidate: a
              material (a material code, every SAP line of it), or a service
              line or line with no material code (by its description).
              Numbers come from SAP; a PUR case's own data that SAP does not
              show is the knowledge graph's (the kg_* tools).
  count()     how many of each the records are, in the words SAP's data
              gives them: "12 materials, 3 service lines".
  check()     1f: the agent's question, its options placed by the data. The
              agent gives each option a label and the words its records
              carry, as the records write them ("0-200", "U320"); the harness
              puts each record under the first option whose words it carries,
              so every count is the data's. Refused, with the reason, when an
              option's words are in no record or in every record, when a
              number its label states is missing from a record it got, or
              when fewer than two options get records of their own; the
              records no option reaches go under "Something else".
  answer()    1f: the officer's answer, an option or their own words; words
              every remaining record does not carry narrow to those that do.
  found_by()  where SAP's record carries the material's words: its short
              text, its long text only, or neither (found by meaning).
  tenders()   the past tenders behind one item's records, latest first:
              ordered and delivered, then ordered, then raised.
  coverage()  1j: the PUR cases ranked by how many of the need's materials
              each holds (the cart's picked codes, and the materials not
              taken forward too). The PUR holding the most is 100%; one
              holding them all is 100% only when it holds them all.

Nothing here decides what to ask: the agent does, and this checks it.
"""

from __future__ import annotations

import re

from waku.nam import guard

TOP_K = 50                 # the KG server's most per search
MAX_OPTIONS = 8
OTHER = "Something else"
_WORD = re.compile(r"[a-z0-9][a-z0-9.#/-]*")
_NUM = re.compile(r"\d+(?:\.\d+)?")
# the count an option's label carries: "(12 materials, 3 service lines)"
_COUNT = re.compile(r"\s*\((?:\d+\s+[a-z ]+?(?:,\s*)?)+\)\s*$", re.IGNORECASE)
_VALUE = re.compile(r"\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?")


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def words(text: str) -> list[str]:
    return [_stem(w.strip(".-/")) for w in _WORD.findall(guard.plain(text or "").lower())
            if w.strip(".-/")]


def norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s.#/-]", " ", _COUNT.sub("", text or "").lower()).split())


def _numbers(text: str) -> set[str]:
    return {n.rstrip("0").rstrip(".") if "." in n else n.lstrip("0") or "0"
            for n in _NUM.findall(guard.plain(text or ""))}


# -- 1d: the records -------------------------------------------------------------

def _sap(data: dict) -> list[dict]:
    out: dict[str, dict] = {}
    for res in (data or {}).get("results") or []:
        codes = res.get("codes") or {}
        for ln in res.get("lines") or []:
            if not isinstance(ln, dict):
                continue
            code = str(ln.get("material") or "").strip()
            desc = " ".join(str(codes.get(code) or ln.get("material_name")
                                or res.get("description") or "").split())
            key = code or "SAP:" + desc.lower()[:60]
            c = out.setdefault(key, {"key": key, "source": "sap", "code": code,
                                     "description": desc, "text": "", "lines": []})
            extra = " ".join(str(ln.get(k) or "") for k in ("long_text", "job"))
            if extra.strip() and extra not in c["text"]:
                c["text"] = (c["text"] + " " + " ".join(extra.split()))[:800]
            c["lines"].append({k: ln.get(k) for k in (
                "kind", "doc_no", "date", "quantity", "unit", "rate_inr", "pr_no", "po_no",
                "pur_case_id", "status", "delivery_date")})
    for c in out.values():
        c["lines"].sort(key=lambda x: str(x.get("date") or ""), reverse=True)
    return list(out.values())


def find(kg_url: str, query: str, call=None) -> tuple[list[dict], list[str]]:
    """(candidates, problems) for the item from SAP; an outage is a problem
    named, never "no record"."""
    from waku.nam import kg_mcp

    call = call or kg_mcp.call
    try:
        data = call(kg_url, "sap_search", query=guard.plain(query).strip(), top_k=TOP_K)
    except Exception as exc:  # noqa: BLE001 - said, never hidden
        return [], [f"SAP could not be read ({type(exc).__name__})"]
    return _sap(data if isinstance(data, dict) else {}), []


def found_by(c: dict, query: str) -> str:
    """'short text' when the record's short text (its description or code)
    carries the material's words, 'long text' when only its long text does,
    'meaning' when neither (SAP's search found it by meaning: BiMet is
    Bimetallic)."""
    ws = words(query)
    if not ws:
        return "meaning"
    if carries({"description": c.get("description") or "", "code": c.get("code") or "",
                "text": ""}, ws):
        return "short text"
    if carries({"description": "", "code": "", "text": c.get("text") or ""}, ws):
        return "long text"
    return "meaning"


def found(cands: list[dict], query: str) -> str:
    """'9 by short text, 3 by long text only, 1 by meaning'."""
    by: dict[str, int] = {}
    for c in cands:
        f = found_by(c, query)
        by[f] = by.get(f, 0) + 1
    said = {"short text": "by short text", "long text": "by long text only",
            "meaning": "by meaning"}
    return ", ".join(f"{by[k]} {v}" for k, v in said.items() if by.get(k))


def unit(c: dict) -> str:
    """What one record is: a material (it has a material code), a service
    line, or a line with no material code."""
    if c.get("code"):
        return "material"
    kinds = {str(ln.get("kind") or "").upper() for ln in c.get("lines") or []}
    return "service line" if "SERVICE" in kinds else "line"


_PLURAL = {"material": "materials", "service line": "service lines", "line": "lines"}


def count(cands: list[dict]) -> str:
    """'12 materials, 3 service lines': the records counted by what they are."""
    by: dict[str, int] = {}
    for c in cands:
        by[unit(c)] = by.get(unit(c), 0) + 1
    return ", ".join(f"{n} {w if n == 1 else _PLURAL[w]}"
                     for w, n in sorted(by.items(), key=lambda wn: list(_PLURAL).index(wn[0])))


# -- matching words ---------------------------------------------------------------

def _haystack(c: dict) -> list[str]:
    """The record's words, each also by its parts and its numbers: "0-700cel"
    is "0700cel", "0", "700cel" and "700", so "0-700", "700" and "700cel" all
    find it; "u320t50" holds "320"."""
    out = []
    for h in words(" ".join(str(x or "") for x in (c["description"], c["code"], c["text"]))):
        out.append(h.replace("-", ""))
        out += [part for part in re.split(r"[-/]", h) if part]
        # and its numbers on their own: "u320t50" and "u320mm" both hold "320"
        out += re.findall(r"\d+(?:\.\d+)?", h)
    return out


def carries(c: dict, ws: list[str]) -> bool:
    """True when the record has every word: a word may begin one ("u320" in
    "u320mm"), but "0-100" never begins "0-1000"."""
    have = _haystack(c)

    def has(w: str) -> bool:
        w = w.replace("-", "")
        return any(h == w or (h.startswith(w) and not (w[-1:].isdigit() and h[len(w)].isdigit()))
                   for h in have)
    return bool(ws) and all(has(w) for w in ws)


# -- 1f: the question ---------------------------------------------------------------

class Refused(Exception):
    """The question does not stand on the records: the reason says why."""


def check(question: str, options: list, cands: list[dict]) -> dict:
    """The question with each option's records, placed by the data."""
    n = len(cands)
    question = " ".join(str(question or "").split())
    raw = options if isinstance(options, list) else []
    if not question or not 2 <= len(raw) <= MAX_OPTIONS:
        raise Refused(f"give one question and 2 to {MAX_OPTIONS} options")
    out, seen, placed, notes = [], set(), set(), []
    for o in raw:
        o = o if isinstance(o, dict) else {"label": str(o), "words": [str(o)]}
        label = " ".join(str(o.get("label") or "").split())[:70]
        said = o.get("words") if isinstance(o.get("words"), list) else [o.get("words") or label]
        ws = [w for x in said for w in words(str(x or ""))]
        if not label or norm(label) in seen:
            raise Refused("every option needs its own label")
        hit, ws, dropped = _relaxed(ws, cands, label)
        if not hit:
            raise Refused(f"no record carries {ws} (option '{label}'): use words as the "
                          f"records write them{_samples(ws, cands)}")
        if dropped:
            notes.append(f"'{label}': matched on {ws}, {dropped} set aside")
        if len(hit) == n:
            raise Refused(f"every record carries {ws}: option '{label}' tells none apart")
        items = [i for i in hit if i not in placed]
        for i in items:
            c = cands[i]
            missing = _numbers(label) - _numbers(f"{c['description']} {c['code']} {c['text']}")
            if missing:
                raise Refused(f"option '{label}' gets '{c['description'][:60]}', which does not "
                              f"carry {sorted(missing)[0]}: fix its words or its label")
        seen.add(norm(label))
        placed.update(items)
        if items:
            out.append({"label": label, "keys": [cands[i]["key"] for i in items],
                        "count": count([cands[i] for i in items])})
    lost = [i for i in range(n) if i not in placed]
    if len(out) < 2:
        raise Refused("the options must split the records: at least two options need "
                      "records of their own")
    if lost:
        out.append({"label": OTHER, "keys": [cands[i]["key"] for i in lost],
                    "count": count([cands[i] for i in lost])})
    if len(out) < 2:
        raise Refused("the options must split the records")
    return {"question": question, "options": out, "notes": notes}


def _relaxed(ws: list[str], cands: list[dict],
             label: str = "") -> tuple[list[int], list[str], list[str]]:
    """(the records hit, the words used, the words dropped). Every word, when
    some record carries them all; else the largest set of them some record
    carries ("0-200" alone when SAP writes "0-200Cel" and "0-200 DegC" and the
    option said both "0-200" and "DegC"). When the label states a number,
    the option is the words carrying it and the words the label names:
    "0-200 °C" with words "0-200" and "DegC" is every record of 0-200,
    whichever way it writes the unit. A word whose number the label states
    is never dropped."""
    from itertools import combinations

    stated = _numbers(label)
    key = [w for w in ws if _numbers(w) and _numbers(w) <= stated]
    if key:
        # the label states its range or size: the option is those words, and
        # the words it does not state (a unit SAP writes two ways) only narrow
        # it where the label says them too
        said = {w.replace("-", "") for w in words(label)}
        use = key + [w for w in ws if w not in key and w.replace("-", "") in said]
        if len(use) < len(ws):
            hit = [i for i, c in enumerate(cands) if carries(c, use)]
            if hit:
                return hit, use, [w for w in ws if w not in use]
    hit = [i for i, c in enumerate(cands) if carries(c, ws)]
    if hit or len(ws) < 2:
        return hit, ws, []
    rest = [w for w in ws if w not in key]
    for size in range(len(rest) - 1, -1, -1):
        best: tuple[list[int], list[str]] = ([], [])
        for sub in combinations(rest, size):
            use = key + list(sub)
            if not use:
                continue
            h = [i for i, c in enumerate(cands) if carries(c, use)]
            if len(h) > len(best[0]):
                best = (h, use)
        if best[0]:
            return best[0], best[1], [w for w in ws if w not in best[1]]
    return [], ws, []


def _samples(ws: list[str], cands: list[dict]) -> str:
    """How the records write what the option was after: descriptions that
    carry one of its words, to copy the words from."""
    seen = []
    for w in ws:
        for c in cands:
            if carries(c, [w]) and c["description"] not in seen:
                seen.append(c["description"])
                break
    return (". Records carrying some of them: " + "; ".join(f"'{d[:60]}'" for d in seen[:3])
            if seen else ". No record carries any of these words.")


def labels(pending: dict) -> list[str]:
    """Each option with the number beside it, counted from SAP and named by
    what it counts: "0-200 °C (7 materials)"."""
    return [f"{o['label']} ({o.get('count') or len(o['keys'])})" for o in pending["options"]]


def answer(pending: dict | None, cands: list[dict], text: str) -> tuple[list[str], str] | None:
    """(the keys the answer keeps, how it was read), or None when it fits no
    option and no remaining record carries its words."""
    said = norm(text)
    for o in (pending or {}).get("options") or []:
        if norm(o["label"]) == said:
            return o["keys"], f"option '{o['label']}'"
    ws = words(text)
    full = [c["key"] for c in cands if carries(c, ws)]
    # the numbers typed are what the officer means ("320 mm" is every 320,
    # "U320mm" and "U320T50" alike); the other words narrow only when no
    # record is lost by the numbers alone
    nums = [w for w in ws if _numbers(w) and not re.search(r"[a-z]", w)]
    by_num = [c["key"] for c in cands if carries(c, nums)] if nums and nums != ws else []
    if len(by_num) > len(full):
        return by_num, f"the numbers {nums}"
    if full:
        return full, f"the words {ws}"
    return None


# -- 1i: the tenders ---------------------------------------------------------------

_ORDER = {"delivered": 0, "ordered": 1, "raised": 2, "cancelled": 3}


def _status(lines: list[dict]) -> str:
    if any("cancel" in str(ln.get("status") or "").lower()
           or "delet" in str(ln.get("status") or "").lower() for ln in lines):
        return "cancelled"
    if any(ln.get("delivery_date") for ln in lines if ln.get("kind") in ("PO", "SERVICE")):
        return "delivered"
    if any(ln.get("po_no") or ln.get("kind") in ("PO", "SERVICE") for ln in lines):
        return "ordered"
    return "raised"


def tenders(cands: list[dict]) -> list[dict]:
    """The PUR cases behind the records, ranked as 1i says: by status
    (delivered, ordered, raised, cancelled), latest first within each."""
    by: dict[str, dict] = {}
    for c in cands:
        for ln in c["lines"]:
            pur = ln.get("pur_case_id")
            if not pur:
                continue
            t = by.setdefault(pur, {"pur": pur, "lines": [], "records": set()})
            t["lines"].append(ln)
            t["records"].add(c.get("code") or c["key"])
    out = []
    for t in by.values():
        dates = [str(ln.get("date")) for ln in t["lines"] if ln.get("date")]
        out.append({"pur": t["pur"], "status": _status(t["lines"]),
                    "latest": max(dates) if dates else "",
                    "po": sorted({str(ln["po_no"]) for ln in t["lines"] if ln.get("po_no")}),
                    "pr": sorted({str(ln["pr_no"]) for ln in t["lines"] if ln.get("pr_no")}),
                    "records": sorted(t["records"]), "tender_no": t.get("tender_no"),
                    "job_name": t.get("job_name")})
    out.sort(key=lambda t: t["latest"], reverse=True)
    out.sort(key=lambda t: _ORDER[t["status"]])
    return out


def coverage(items: list[dict]) -> dict:
    """1j: the PUR cases ranked by how many of the need's materials each
    holds. items: {name, chosen, picked (the cart's record or None), records
    (the records that stand for it: the picked one, else those still in, or
    every record found for a material not taken forward)}.

    A PUR holds a material when one of its SAP lines is one of the material's
    records; for a material in the cart, that is the very code picked, and
    the PUR's PR and PO for it are named. The PUR holding the most materials
    is 100%; the rest are their share of that most ("2 of 3 materials" is
    67% when one PUR holds all three, 100% when none holds more than two)."""
    by: dict[str, dict] = {}
    for it in items:
        for c in it["records"]:
            for ln in c.get("lines") or []:
                pur = ln.get("pur_case_id")
                if not pur:
                    continue
                t = by.setdefault(pur, {"pur": pur, "lines": [], "items": {}})
                t["lines"].append(ln)
                t["items"].setdefault(it["name"], set()).add(c.get("code") or c["key"])
    names = [it["name"] for it in items]
    cart = {it["name"] for it in items if it.get("picked")}
    out = []
    for t in by.values():
        dates = [str(ln.get("date")) for ln in t["lines"] if ln.get("date")]
        out.append({"pur": t["pur"], "status": _status(t["lines"]),
                    "latest": max(dates) if dates else "",
                    "items": [n for n in names if n in t["items"]],
                    "codes": {n: sorted(t["items"][n]) for n in names if n in t["items"]},
                    "cart": len(cart & set(t["items"])),
                    "pr": sorted({str(ln["pr_no"]) for ln in t["lines"] if ln.get("pr_no")}),
                    "po": sorted({str(ln["po_no"]) for ln in t["lines"] if ln.get("po_no")})})
    most = max((len(t["items"]) for t in out), default=0)
    for t in out:
        t["match"] = round(100 * len(t["items"]) / most) if most else 0
        t["covers"] = f"{len(t['items'])} of {len(names)} materials"
    out.sort(key=lambda t: t["latest"], reverse=True)
    out.sort(key=lambda t: (-len(t["items"]), -t["cart"], _ORDER[t["status"]]))
    return {"total": len(names), "most": most, "cart": sorted(cart), "purs": out,
            "all": bool(out) and most == len(names)}


# -- what the agent reads to choose its question ---------------------------------

def digest(cands: list[dict], limit: int = 40) -> str:
    """The records as the agent reads them to choose its next question: the
    kinds (each description's first word), the words that split them (in some
    records but not all, with how many carry each) and the records in short.
    Everything is counted from the records; nothing names a detail to ask."""
    n = len(cands)
    kinds: dict[str, int] = {}
    for c in cands:
        first = (_WORD.findall(guard.plain(c["description"]).lower()) or ["-"])[0]
        kinds[first] = kinds.get(first, 0) + 1
    seen: dict[str, int] = {}
    for c in cands:
        text = guard.plain(f"{c['description']} {c['text']}")
        # the same text a question's words are matched on (the description and
        # SAP's long text); its words, and its numbers and ranges on their own: "0-200Cel" and
        # "0-200 DegC" are both the value 0-200, "U320mm" and "U320T50" both 320
        values = {w for w in words(text) if len(w) > 1}
        values |= {re.sub(r"\s+", "", v) for v in _VALUE.findall(text)}
        for w in values:
            seen[w] = seen.get(w, 0) + 1
    split = sorted(((w, k) for w, k in seen.items() if 1 < k < n),
                   key=lambda wk: (abs(wk[1] - n / 2), -wk[1], wk[0]))[:30]
    out = [f"{count(cands)}.",
           "Kinds (first word of the description): "
           + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items(),
                                                    key=lambda kv: (-kv[1], kv[0]))[:12])
           + ".",
           "Words that split them (records carrying each): "
           + (", ".join(f"{w} {k}" for w, k in split) or "none") + ".",
           "Records (key: description):"]
    out += [f"- {c['key']}: {guard.sanitise(c['description'], 90)}" for c in cands[:limit]]
    if n > limit:
        out.append(f"(+{n - limit} more)")
    same = _same_short_text(cands)
    if same:
        out.append("Same short text, different material codes (only the long text tells "
                   "them apart):")
        out += same
    return "\n".join(out)


def _same_short_text(cands: list[dict], limit: int = 6) -> list[str]:
    """For each short text several codes share, the words of each code's long
    text the others' lack: what a question must ask to tell them apart."""
    groups: dict[str, list[dict]] = {}
    for c in cands:
        groups.setdefault(norm(c["description"]), []).append(c)
    out = []
    for group in [g for g in groups.values() if len(g) > 1][:limit]:
        own = [set(words(c.get("text") or "")) for c in group]
        parts = []
        for c, ws in zip(group, own, strict=True):
            others = set().union(*(o for o in own if o is not ws)) if len(own) > 1 else set()
            diff = sorted(w for w in ws - others if len(w) > 1)[:8]
            parts.append(f"{c['key']}: {', '.join(diff) if diff else 'no long text of its own'}")
        out.append(f"- '{guard.sanitise(group[0]['description'], 70)}' ({len(group)} codes): "
                   + "; ".join(parts))
    return out
