"""The agent's tools for the PR Creation Flow: each does one step and keeps
the case; each gate the manual sets is checked here, in code.

  nam_need      1a-1c  open the chat's case for the job description, with the
                       materials it names: each is searched in SAP at once
                       and counted (by short text, by long text)
  nam_choose    1d     ask which materials go forward, or record the choice
  nam_search           search one item again, with other words
  nam_ask       1f     a question whose options the records bear out
  nam_answer    1f-1g  the officer's answer: narrows the records, or records
                       a detail (default=true: NRL's standard value, with
                       its source)
  nam_pick      1h     the one material for the item, put in the cart (or
                       taken out); then the next chosen item
  nam_tenders   1j     the PURs holding the most of the need's materials
                       (no item), or one item's past tenders
  nam_estimate  2a-2f  the cart's estimate, only when the officer asks
  nam_pr        3a-3b  each cart item's own PR: fill, set, confirm
  nam_undo             take back the officer's last act(s)
  nam_case             the chat's case as it stands, or another case resumed

The agent decides when to call which (flow.py is its guide). A tool that
refuses says why in its reply, so the agent can put it right. Every call is
one audit row; every write is a new version of the case (case.py).
"""

from __future__ import annotations

import re
import time
from datetime import date
from pathlib import Path

from waku.nam import audit, case, chatstate, estimate, guard, narrow, permissions, pr
from waku.tools.registry import Tool

CATEGORIES = ("goods", "services", "works")
SHOW = 25             # records listed in a reply; the rest are counted
ALL = "All of them"   # the choice of every material that has records
UNDO_WORDS = ("undo", "go back", "back", "take it back")


class Stop(Exception):
    """The step cannot go on: the message goes back to the agent."""


def _rs(v) -> str:
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "-"


def records_table(cands: list[dict], limit: int = SHOW) -> str:
    rows = ["| Key | Is | Description | Last order (date, rate INR) | PUR |",
            "|---|---|---|---|---|"]
    for c in cands[:limit]:
        last = next((ln for ln in c["lines"] if ln.get("kind") in ("PO", "SERVICE")
                     and ln.get("rate_inr")), None) or (c["lines"][0] if c["lines"] else {})
        doc = last.get("po_no") or last.get("doc_no") or "-"
        pur = last.get("pur_case_id") or "-"
        rows.append(f"| {c['key']} | {narrow.unit(c)} | "
                    f"{guard.sanitise(c['description'], 80).replace('|', '/')} | "
                    f"{doc} ({last.get('date') or '-'}, {_rs(last.get('rate_inr'))}) | {pur} |")
    if len(cands) > limit:
        rows.append(f"(+{len(cands) - limit} more)")
    return "\n".join(rows)


PICK_FROM = 3          # records few enough to show the officer as a table to pick from


def _view(left: list[dict]) -> str:
    """What the agent gets back after a search or an answer: the records as
    a table when few are left to pick from; else the digest it reads to
    choose the next question, which is not for the officer's eyes."""
    if len(left) <= PICK_FROM:
        return (records_table(left) + "\nFew enough to pick from: show them, and pick the "
                "officer's choice with nam_pick (key, quantity, unit).")
    return ("FOR YOU, NOT TO SHOW: the records still in, to choose the next question from.\n"
            + narrow.digest(left) + "\nDo not paste these records. Read the need back in one "
            "line, say how many records are in, and ask ONE question about the one detail that "
            "best splits them, with nam_ask.")


class Steps:
    """The tools, bound to the database, the home folder and the KG."""

    def __init__(self, conn, home: Path, kg_url: str, call=None):
        self.conn, self.home, self.kg_url, self.call = conn, Path(home), kg_url, call
        self.refusals: dict[str, int] = {}     # refusals in a row, per chat

    # -- plumbing -----------------------------------------------------------------

    def _session(self) -> str:
        return chatstate.current()

    def _case(self) -> dict:
        data = case.for_session(self.conn, self._session())
        if data is None:
            raise Stop("No case is open in this chat: call nam_need with the officer's need "
                       "first.")
        return data

    def _item(self, data: dict, name: str, working: bool = True) -> dict:
        """The item named; '' is the item being worked now. working: it must
        be one the officer takes forward."""
        name = narrow.norm(name) if name else ""
        it = case.item(data, name) if name else (case.current_item(data)
                                                 or case.item(data, ""))
        if it is None:
            raise Stop(f"No item '{name}' in {data['case_id']}; its items are: "
                       + ", ".join(i["name"] for i in data["items"]) + ".")
        undecided = not any("selected" in i for i in data["items"])
        if working and undecided and sum(1 for i in data["items"] if i.get("candidates")) > 1:
            raise Stop("The officer has not chosen which materials go forward yet: ask with "
                       "nam_choose(question=...), or read their choice with "
                       "nam_choose(items=[...]).")
        if working and it.get("selected") is False:
            raise Stop(f"'{it['name']}' was not taken forward. To work it, add it to the "
                       "chosen items with nam_choose.")
        return it

    def _save(self, data: dict, act: str = "", did: str = "") -> dict:
        return case.save(self.conn, data, self._session(), act, did)

    def _run(self, name: str, fn, **args) -> str:
        """One tool call: the step, its audit row, and a refusal as text."""
        t0, status, out, cid = time.perf_counter(), "ok", "", ""
        try:
            out, cid = fn(**args)
        except (Stop, narrow.Refused, ValueError, permissions.Forbidden, case.NotYours,
                case.Stale) as exc:
            status = "refused"
            out = (f"REFUSED: {exc}" if not isinstance(exc, case.Stale) else
                   "REFUSED: the case changed meanwhile; read it with nam_case and try again.")
        chat = self._session()
        self.refusals[chat] = self.refusals.get(chat, 0) + 1 if status == "refused" else 0
        if self.refusals[chat] >= 3:
            out += (f" This is refusal {self.refusals[chat]} in a row: stop retrying. Tell the "
                    "officer in plain words what you found and ask them directly.")
        try:
            audit.record(self.conn, kind="tool", name=name, status=status, case_id=cid,
                         ms=int((time.perf_counter() - t0) * 1000),
                         detail={"args": {k: str(v)[:80] for k, v in args.items()
                                          if k != "_notify"}})
        except Exception:  # noqa: BLE001 - the audit row is best effort in a chat turn
            pass
        return out

    def _may(self, action: str) -> None:
        permissions.require(case.current().roles, action)

    def _not_asked(self) -> None:
        if chatstate.asked():
            raise Stop(f"You asked \"{chatstate.asked()}\" in this turn: the officer has not "
                       "answered yet. Stop and wait for their reply.")

    def _lookup(self, it: dict, query: str = "") -> list[str]:
        """Search SAP for the item; its records replace the old ones. The
        problems named (an outage is never "no record")."""
        q = (query or it["name"]).strip()
        cands, problems = narrow.find(self.kg_url, q, self.call)
        if not cands and problems:
            return problems
        it.update(query=q, searched=True, candidates=cands, keys=[c["key"] for c in cands],
                  trail=[], pending=None, picked=None)
        return problems

    # -- 1a-1c ---------------------------------------------------------------------

    def need(self, need: str = "", category: str = "", items=None, new: bool = False):
        self._may("need")
        category = (category or "").strip().lower()
        if category and category not in CATEGORIES:
            raise Stop("category is goods, services or works")
        names = [" ".join(str(i).split()) for i in (items or []) if str(i).strip()]
        data = None if new else case.for_session(self.conn, self._session())
        if data is None:
            if not (need or "").strip():
                raise Stop("Give the officer's need, in their words.")
            data = case.open_case(self.conn, self._session(), need.strip(), category)
        if need.strip():
            data["need"] = need.strip()
        if category:
            data["category"] = category
        if names or not data["items"]:
            have = {i["name"].lower(): i for i in data["items"]}
            before = set(have)
            data["items"] = [have.get(n.lower()) or {"name": n, "searched": False}
                             for n in (names or [data["need"]])]
            if {i["name"].lower() for i in data["items"]} != before:
                # other materials: the choice of what goes forward is made again
                for i in data["items"]:
                    i.pop("selected", None)
                data["choosing"] = None
        # 1c: each material is searched in SAP at once, so the officer sees
        # how many SAP holds of each before choosing what goes forward
        problems = []
        for it in data["items"]:
            if not it.get("searched"):
                problems += [f"'{it['name']}': {p}" for p in self._lookup(it)]
        offer = [it for it in data["items"] if it.get("candidates")]
        if len(data["items"]) == 1 and offer:
            data["items"][0]["selected"] = True
        data = self._save(data, "need", f"set the need and its {len(data['items'])} material(s)")
        chatstate.set_case_open(True)       # from now in this turn too, not only the next
        rows = ["| # | Material | In SAP | Found by |", "|---|---|---|---|"]
        for n, it in enumerate(data["items"], 1):
            cands = it.get("candidates") or []
            rows.append(f"| {n} | {it['name']} | "
                        f"{narrow.count(cands) or ('not searched' if not it.get('searched') else 'none')}"
                        f" | {narrow.found(cands, it.get('query') or it['name']) or '-'} |")
        capped = [it["name"] for it in data["items"]
                  if len(it.get("candidates") or []) >= narrow.TOP_K]
        notes = ""
        if capped:
            notes += (f"\nSAP's search gives at most {narrow.TOP_K} records: "
                      f"{', '.join(capped)} may have more.")
        if problems:
            notes += "\nNot searched: " + "; ".join(problems) + "."
        if any("selected" in it for it in data["items"]) and len(data["items"]) > 1:
            nxt = "the officer's choice stands; nam_choose changes it."
        elif len(offer) > 1:
            nxt = ("show this table and ask which materials go forward with nam_choose "
                   "(question=..., no items): the harness puts the options and counts.")
        elif data["items"][0].get("selected"):
            it = data["items"][0]
            nxt = (f"work '{it['name']}'.\n{_view(case.remaining(it))}"
                   if it.get("candidates") else "")
        else:
            nxt = ("SAP holds no record for these materials: ask the officer to describe them "
                   "another way (their usual names, a size, a material code).")
        return (f"{data['case_id']}: the need holds {len(data['items'])} material(s).\n"
                + "\n".join(rows) + notes + f"\nNext: {nxt}", data["case_id"])

    # -- 1d: which items go forward -------------------------------------------------

    def choose(self, question: str = "", items=None, _notify=None):
        self._may("need")
        data = self._case()
        offer = [it for it in data["items"] if it.get("candidates")]
        if not items:
            if not (question or "").strip():
                raise Stop("Give the question in your words (which materials go forward), or "
                           "items= with the officer's choice.")
            if len(offer) < 2:
                raise Stop("There is no choice to ask: "
                           + (f"only '{offer[0]['name']}' has records." if offer else
                              "no material has records."))
            opts = [f"{it['name']} ({narrow.count(it['candidates'])})" for it in offer]
            opts.append(ALL)
            data["choosing"] = {"question": " ".join(question.split()), "options": opts}
            data = self._save(data, "ask", "asked which materials go forward")
            shown = {"question": data["choosing"]["question"], "options": opts, "field": "nam"}
            if _notify:
                _notify("ask_options", shown)
            chatstate.mark_asked(shown["question"])
            return (f"Asked: \"{shown['question']}\" Options: {' | '.join(opts)}. The officer "
                    "may choose several. Stop here and wait.", data["case_id"])
        self._not_asked()
        said = [narrow.norm(str(x)) for x in (items if isinstance(items, list) else [items])]
        if any(x in (narrow.norm(ALL), "all") for x in said):
            picked = offer
        else:
            picked, unknown = [], []
            for x in said:
                it = (data["items"][int(x) - 1] if x.isdigit() and 0 < int(x) <= len(
                    data["items"]) else case.item(data, x))
                if it is None:
                    unknown.append(x)
                elif it not in picked:
                    picked.append(it)
            if unknown:
                raise Stop(f"No material {unknown} in the need; they are: "
                           + ", ".join(it["name"] for it in data["items"]) + ".")
        if not picked:
            raise Stop("Choose at least one material.")
        locked = case.confirmed(data) - {it["name"] for it in picked}
        if locked:
            raise Stop(f"{', '.join(sorted(locked))} has a confirmed PR: it stays chosen.")
        order = picked + [it for it in data["items"] if it not in picked]
        for it in order:
            it["selected"] = it in picked
            if not it["selected"]:
                it["picked"], it["pending"], it["pr"] = None, None, None
        data["items"], data["choosing"], data["matched"] = order, None, None
        data = self._save(data, "choose", "chose " + ", ".join(it["name"] for it in picked))
        now = case.current_item(data)
        dropped = [it["name"] for it in data["items"] if not it["selected"]]
        out = (f"Taken forward, in this order: {', '.join(it['name'] for it in picked)}."
               + (f" Not taken: {', '.join(dropped)}." if dropped else ""))
        if now is not None:
            out += (f"\nNow '{now['name']}' (one item at a time): SAP has "
                    f"{narrow.count(case.remaining(now)) or 'nothing'} still in.\n"
                    + _view(case.remaining(now)))
        return out, data["case_id"]

    # -- searching again --------------------------------------------------------------

    def search(self, item: str = "", query: str = "", restart: bool = False):
        self._may("need")
        data = self._case()
        it = self._item(data, item, working=False)
        if it.get("pending"):
            raise Stop(f"'{it['name']}' has the open question \"{it['pending']['question']}\": "
                       "the officer's message is most likely its answer, so read it with "
                       "nam_answer first. If the officer wants another item instead, add it "
                       "with nam_need.")
        if not restart and it.get("answers"):
            raise Stop(f"'{it['name']}' is already narrowed by {len(it['answers'])} answer(s): "
                       "call nam_answer or nam_ask. To search again anyway (the answers still "
                       "apply to the new records), pass restart=true.")
        answers = list(it.get("answers") or [])
        problems = self._lookup(it, query)
        if not it.get("candidates") and problems:
            raise Stop("; ".join(problems) + ". SAP is unavailable: say so, and offer to try "
                       "again.")
        q, cands = it["query"], it["candidates"]
        # the officer's answers so far still hold: they narrow the new records
        keys, kept = [c["key"] for c in cands], []
        for a in answers:
            read = narrow.answer(None, [c for c in cands if c["key"] in set(keys)], a["answer"])
            if read is not None:
                keys = read[0]
                kept.append(a["answer"])
        it.update(keys=keys, answers=[a for a in answers if a["answer"] in kept])
        data = self._save(data, "search", f"searched '{q}' for '{it['name']}'")
        warn = (" (" + "; ".join(problems) + ")") if problems else ""
        if kept:
            warn += (f". The earlier answers {kept} still apply: {len(keys)} of {len(cands)} "
                     "records are in")
            cands = case.remaining(it)
        if not cands:
            return (f"NO RECORD: SAP holds no PR, PO or service line for '{q}'{warn}. "
                    "Ask the officer to describe it another way (its usual name, a size, a "
                    "material code), then search again.", data["case_id"])
        return (f"SAP has {narrow.count(it['candidates'])} for '{q}' "
                f"({narrow.found(it['candidates'], q)}){warn}.\n{_view(cands)}",
                data["case_id"])

    # -- 1f ------------------------------------------------------------------------

    def ask(self, item: str = "", question: str = "", options=None, _notify=None):
        data = self._case()
        it = self._item(data, item)
        left = case.remaining(it)
        if len(left) < 2:
            raise Stop(f"{len(left)} record left for '{it['name']}': nothing to tell apart. "
                       "Show it and put it in the cart with nam_pick, or search again.")
        q = narrow.check(question, options or [], left)
        it["pending"] = q
        data = self._save(data, "ask", f"asked \"{q['question']}\" for '{it['name']}'")
        shown = {"question": q["question"], "options": narrow.labels(q), "field": "nam"}
        if _notify:
            _notify("ask_options", shown)
        chatstate.mark_asked(q["question"])
        notes = (" Note: " + "; ".join(q["notes"]) + ".") if q.get("notes") else ""
        return (f"Asked: \"{q['question']}\" Options: {' | '.join(shown['options'])}.{notes} "
                "The officer has not answered yet: stop here and wait.", data["case_id"])

    def answer(self, item: str = "", answer: str = "", field: str = "", value: str = "",
               default: bool = False, source: str = ""):
        self._not_asked()
        if narrow.norm(answer) in UNDO_WORDS:
            return self.undo()
        data = self._case()
        it = self._item(data, item)
        if field:
            if not str(value).strip():
                raise Stop("Give the detail's value.")
            if default and not source.strip():
                raise Stop("A default value needs its source (the NRL specification clause).")
            it.setdefault("details", {})[field.strip().lower()] = {
                "value": " ".join(str(value).split()), "default": bool(default),
                "source": source.strip()[:200]}
            # a value some of the records carry and some do not tells them apart
            # too: it narrows them, as an answer would
            left, note = case.remaining(it), ""
            plain = re.fullmatch(r"[\d.,]+|\d{4}-\d{2}-\d{2}", str(value).strip())
            read = (None if default or not left or plain  # a count or a date names no record
                    else narrow.answer(None, left, str(value)))
            if read is not None and 0 < len(read[0]) < len(left):
                it["keys"] = [k for k in it["keys"] if k in set(read[0])]
                it.setdefault("answers", []).append({"question": field, "answer": str(value)})
                note = f" It also narrows the records: {len(it['keys'])} still in.\n"
                note += _view(case.remaining(it))
            data = self._save(data, "detail", f"recorded {field} = {value} for '{it['name']}'")
            return (f"Recorded {field} = {value}" + (" (NRL default)" if default else "")
                    + f" for '{it['name']}'." + note, data["case_id"])
        left = case.remaining(it)
        read = narrow.answer(it.get("pending"), left, answer)
        if read is None:
            raise Stop(f"'{answer}' fits no option and no remaining record carries its words. "
                       "Ask ONE short question to clarify; do not restart.")
        keys, how = read
        keep = [k for k in it["keys"] if k in set(keys)]
        question = (it.get("pending") or {}).get("question") or "(the officer's own words)"
        it.setdefault("answers", []).append({"question": question, "answer": answer})
        it["keys"], it["pending"] = keep, None
        data = self._save(data, "answer", f"the answer '{answer}' to \"{question}\" for "
                                          f"'{it['name']}'")
        left = case.remaining(it)
        return (f"Read as {how}: {narrow.count(left) or 'nothing'} still in for "
                f"'{it['name']}'.\n"
                f"{_view(left)}", data["case_id"])

    # -- 1h: the cart ----------------------------------------------------------------

    def pick(self, item: str = "", key: str = "", quantity=None, unit: str = "",
             remove: bool = False):
        self._may("need")
        self._not_asked()
        data = self._case()
        if remove:
            it = self._item(data, item, working=False)
            if not it.get("picked"):
                raise Stop(f"'{it['name']}' is not in the cart.")
            if it["name"] in case.confirmed(data):
                raise Stop(f"'{it['name']}' has a confirmed PR: it stays in the cart.")
            it["picked"], it["pr"], data["matched"] = None, None, None
            data = self._save(data, "unpick", f"took '{it['name']}' out of the cart")
            return (f"Took '{it['name']}' out of the cart; its records still in: "
                    f"{narrow.count(case.remaining(it)) or 'none'}.", data["case_id"])
        it = self._item(data, item)
        left = case.remaining(it)
        rec = next((c for c in left if c["key"] == key.strip()), None)
        if rec is None:
            found = any(c["key"] == key.strip() for c in it.get("candidates") or [])
            raise Stop(f"'{key}' is "
                       + ("not among the records still in after the officer's answers"
                          if found else "not one of the records found")
                       + f" for '{it['name']}'. Pick a Key from the records still in, or take "
                       "an answer back with nam_undo.")
        if len(left) > PICK_FROM:
            raise Stop(f"{len(left)} records are still in for '{it['name']}': ask what tells "
                       "them apart (nam_ask) until a few are left. If the officer named this "
                       "code themselves, read it with nam_answer(answer=<code>).")
        line = rec["lines"][0] if rec["lines"] else {}
        units = [ln.get("unit") for ln in rec["lines"] if ln.get("unit")]
        it["picked"] = {"key": rec["key"], "code": rec.get("code") or "",
                        "description": rec["description"], "source": rec["source"],
                        "pur": line.get("pur_case_id") or (rec.get("tender") or {}).get("pur"),
                        "quantity": float(quantity) if quantity not in (None, "") else None,
                        "unit": unit or (units[0] if units else ""), "lines": rec["lines"]}
        it["pending"], it["pr"], data["matched"] = None, None, None
        data = self._save(data, "pick", f"put {rec.get('code') or rec['key']} in the cart for "
                                        f"'{it['name']}'")
        cart = [i["name"] for i in case.chosen(data) if i.get("picked")]
        out = (f"In the cart for '{it['name']}': {rec.get('code') or rec['key']} "
               f"{rec['description']} (PUR {it['picked']['pur'] or '-'}), quantity "
               f"{it['picked']['quantity'] or '?'} {it['picked']['unit']}. Cart: {len(cart)} of "
               f"{len(case.chosen(data))} chosen item(s).")
        if not it["picked"]["quantity"]:
            out += " The quantity is still to come: ask how many, in plain words."
        now = case.current_item(data)
        if now is not None:
            out += (f"\nNext item: '{now['name']}': SAP has "
                    f"{narrow.count(case.remaining(now)) or 'nothing'} still in.\n"
                    + _view(case.remaining(now)))
        else:
            out += ("\nEvery chosen item is in the cart. Next: the PURs that hold the need's "
                    "materials (nam_tenders with no item), then each item's PR (nam_pr "
                    "item=..., action='fill'). An estimate for the cart only if the officer asks.")
        return out, data["case_id"]

    # -- 1j: the matching PURs ----------------------------------------------------------

    def tenders(self, item: str = ""):
        data = self._case()
        if item or len(data["items"]) == 1:
            return self._item_tenders(data, item)
        pool = []
        for it in data["items"]:
            if not it.get("candidates"):
                continue
            recs = ([c for c in it["candidates"] if c["key"] == it["picked"]["key"]]
                    if it.get("picked") else
                    case.remaining(it) if it.get("selected") else it["candidates"])
            pool.append({"name": it["name"], "picked": it.get("picked"), "records": recs})
        m = narrow.coverage(pool)
        if not m["purs"]:
            raise Stop("These records name no PUR case.")
        data["matched"] = [{"pur": t["pur"], "match": t["match"], "covers": t["covers"]}
                           for t in m["purs"][:15]]
        data = self._save(data, "match", "ranked the matching PURs")
        rows = ["| Match | PUR | Holds | Materials (codes) | Status | Latest | PR | PO |",
                "|---:|---|---|---|---|---|---|---|"]
        for t in m["purs"][:15]:
            mats = "; ".join(f"{n}: {', '.join(c[:2])}" for n, c in t["codes"].items())
            rows.append(f"| {t['match']}% | {t['pur']} | {t['covers']} | "
                        f"{guard.sanitise(mats, 160).replace('|', '/')} | {t['status']} | "
                        f"{t['latest'] or '-'} | {', '.join(t['pr'][:3]) or '-'} | "
                        f"{', '.join(t['po'][:3]) or '-'} |")
        cart = m["cart"]
        head = (f"The need names {m['total']} material(s); in the cart: "
                f"{', '.join(cart) or 'none yet'}. ")
        head += (f"A PUR holds all {m['total']}: 100%." if m["all"] else
                 f"No PUR holds all {m['total']}: the most any holds is {m['most']}, so a PUR "
                 f"holding {m['most']} is the 100% match.")
        gaps = [t["pur"] for t in m["purs"][:15] if not t["po"] or not t["pr"]]
        tail = ("" if not gaps else "\nSAP shows no PR or PO for " + ", ".join(gaps[:6])
                + ": its tender record in the knowledge graph (kg_tender_record) may.")
        return head + "\n" + "\n".join(rows) + tail, data["case_id"]

    def _item_tenders(self, data: dict, item: str):
        it = self._item(data, item, working=False)
        ranked = narrow.tenders([c for c in it["candidates"] if c["key"] == it["picked"]["key"]]
                                if it.get("picked") else case.remaining(it))
        if not ranked:
            raise Stop("These records name no PUR case.")
        rows = ["| PUR | Status | Latest | PR | PO | Materials |",
                "|---|---|---|---|---|---|"]
        rows += [f"| {t['pur']} | {t['status']} | {t['latest'] or '-'} | "
                 f"{', '.join(t['pr'][:3]) or '-'} | {', '.join(t['po'][:3]) or '-'} | "
                 f"{', '.join(t['records'][:4])} |" for t in ranked[:15]]
        gaps = [t["pur"] for t in ranked[:15] if not t["po"] or not t["pr"]]
        tail = ("" if not gaps else "\nSAP shows no PR or PO for " + ", ".join(gaps)
                + ": its tender record in the knowledge graph (kg_tender_record) may.")
        return (f"Past tenders for '{it['name']}' from SAP, delivered then ordered then "
                "raised, latest first:\n" + "\n".join(rows) + tail, data["case_id"])

    # -- undo ---------------------------------------------------------------------------

    def undo(self, steps: int = 1):
        self._may("need")
        self._not_asked()
        data = self._case()
        data, taken = case.undo(self.conn, data, self._session(), steps)
        now = case.current_item(data)
        out = f"Took back: {'; '.join(taken)}.\n{case.summary(data)}"
        if data.get("choosing"):
            out += "\nThe question of which materials go forward is open again."
        elif now is not None and now.get("pending"):
            out += f"\nThe question \"{now['pending']['question']}\" is open again."
        elif now is not None and now.get("searched"):
            out += "\n" + _view(case.remaining(now))
        return out, data["case_id"]

    # -- stage 2 (optional) -------------------------------------------------------------

    def estimate_step(self, action: str = "show", line: int = 0, quantity=None, rate=None,
                      decision: str = "", note: str = "", evaluation_date: str = ""):
        data = self._case()
        est = data.get("estimate") or {}
        if case.confirmed(data) and action != "show":
            raise Stop("A PR is confirmed: the estimate can no longer change.")
        if action == "build":
            self._may("estimate.build")
            open_items = [i["name"] for i in case.chosen(data) if not i.get("picked")]
            if open_items:
                raise Stop("Put a material in the cart for every chosen item first: "
                           + ", ".join(open_items))
            until = date.fromisoformat(evaluation_date) if evaluation_date else date.today()
            est = estimate.build([{"name": i["name"], "picked": i["picked"]}
                                  for i in case.chosen(data)], until)
        elif action in ("set", "decide", "lock"):
            if not est.get("lines"):
                raise Stop("No estimate yet: nam_estimate(action='build').")
            if est.get("locked") and action != "lock":
                raise Stop("The estimate is locked; build it again to change it.")
            if action == "set":
                estimate.set_line(est, line, quantity, rate)
            elif action == "decide":
                if decision == "revise" and rate is not None:
                    estimate.set_line(est, line, None, rate)
                else:
                    estimate.decide(est, line, decision, note)
            else:
                self._may("estimate.lock")
                left = estimate.blockers(est)
                if left:
                    raise Stop("The estimate cannot be locked yet: " + "; ".join(left) + ".")
                estimate.lock(est)
                self._sheet(data["case_id"], "estimate.xlsx", "Estimate", [
                    ["S.No", "Code", "Description", "Unit", "Quantity", "Unit price", "Total",
                     "Basis", "Source"]] + [[ln["line"], ln["code"], ln["description"],
                                            ln["unit"], ln["quantity"], ln["rate"],
                                            ln["amount"], ln["basis"], ln["source"]]
                                           for ln in est["lines"]])
        elif action != "show":
            raise Stop("action is build, set, decide, lock or show")
        if not est.get("lines"):
            raise Stop("No estimate yet: nam_estimate(action='build').")
        data["estimate"] = est
        data = self._save(data, "estimate" if action != "show" else "",
                          f"estimate: {action}" + (f" line {line}" if line else ""))
        left = estimate.blockers(est)
        tail = ("LOCKED: each item's PR takes its price from it." if est.get("locked") else
                ("Before the lock: " + "; ".join(left) + "." if left else
                 "Every line is settled: the officer may lock it (action='lock')."))
        return f"Estimate for {data['case_id']}:\n{estimate.table(est)}\n{tail}", data["case_id"]

    # -- stage 3: one PR per cart item -------------------------------------------------

    def pr_step(self, item: str = "", action: str = "show", delivery_date: str = "",
                plant: str = "", storage_location: str = "", justification: str = "",
                rate=None, accept_price: bool = False):
        data = self._case()
        if not item.strip():
            ready = [i for i in case.chosen(data) if i.get("picked")
                     and (i.get("pr") or {}).get("status") not in pr.DONE]
            cart = [i for i in case.chosen(data) if i.get("picked")]
            if not ready and len(cart) == 1:
                ready = cart
            if not ready:
                raise Stop("Name the item whose PR this is; the cart holds: "
                           + (", ".join(i["name"] for i in case.chosen(data)
                                        if i.get("picked")) or "nothing yet") + ".")
            it = ready[0]
        else:
            it = self._item(data, item)
        if not it.get("picked"):
            raise Stop(f"'{it['name']}' is not in the cart yet: its material comes first "
                       "(nam_pick).")
        done = (it.get("pr") or {}).get("status") in pr.DONE
        if action in ("fill", "set", "confirm") or not it.get("pr"):
            self._may("pr.fill")
            if not done:
                it["pr"] = pr.fill(data, it)
        given = {k: v for k, v in (("delivery_date", delivery_date), ("plant", plant),
                                   ("storage_location", storage_location),
                                   ("justification", justification)) if v}
        if (given or rate is not None or accept_price) and done:
            raise Stop(f"The PR for '{it['name']}' is confirmed: it can no longer change.")
        if given:
            pr.set_fields(it["pr"], **given)
        if rate is not None or accept_price:
            pr.set_price(it["pr"], rate, accept_price)
        if action == "confirm" and not done:
            self._may("pr.confirm")
            it["pr"]["missing"] = pr.missing(it["pr"])
            if it["pr"]["missing"]:
                raise Stop(f"The PR for '{it['name']}' cannot be confirmed yet; missing: "
                           + "; ".join(it["pr"]["missing"]) + ".")
            it["pr"]["status"] = "ready_for_sap"
        elif action not in ("show", "fill", "set", "confirm"):
            raise Stop("action is fill, set, confirm or show")
        data = self._save(data, "pr" if action != "show" else "",
                          f"PR for '{it['name']}': {action}")
        if action == "confirm":
            self._sheet(data["case_id"], "pr.xlsx", "PR", pr.sheet_rows(data))
        it = case.item(data, it["name"])
        left = [i["name"] for i in case.chosen(data) if (i.get("pr") or {}).get("status")
                not in pr.DONE]
        if it["pr"]["status"] in pr.DONE:
            tail = ("CONFIRMED. SAP's PR interface is not connected yet: the PR is ready for "
                    "SAP and written to the bulk-upload sheet; it has no SAP PR number until "
                    "SAP returns one. Never give a PR number. "
                    + (f"PRs still to do: {', '.join(left)}." if left else
                       "Every chosen item has its PR: the need is done."))
        else:
            tail = ("Show this PR to the officer; ask in plain words for what is missing, and "
                    "on their confirmation, action='confirm'.")
        return f"{pr.table(it['pr'])}\n{tail}", data["case_id"]

    def show(self, case_id: str = ""):
        self._may("case.read")
        if case_id.strip():
            data = case.load(self.conn, guard.plain_ids(case_id).strip().upper())
            if data is None:
                raise Stop(f"No case {case_id}.")
            data = self._save(data, "case", "resumed in this chat")
        else:
            data = self._case()
        from waku.nam import flow

        now, nxt = flow.stage_of(data)
        return f"{case.summary(data)}\nStep now {now}; next {nxt}.", data["case_id"]

    def _sheet(self, case_id: str, name: str, title: str, rows: list[list]) -> Path:
        from waku.nam.xlsx import xlsx

        folder = self.home / "nam" / case_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_bytes(xlsx([(title, rows)]))
        return path


def _tool(name, description, props, required, fn, notify=False) -> Tool:
    return Tool(name=name, description=description,
                input_schema={"type": "object", "properties": props, "required": required},
                fn=fn, wants_notify=notify)


ITEM = {"type": "string", "description": "The item's name as nam_need set it ('' for the item "
                                         "being worked now)"}


def make_tools(conn, home: Path, kg_url: str, call=None) -> list[Tool]:
    s = Steps(conn, home, kg_url, call)
    return [
        _tool("nam_need", "PR Creation Flow 1a-1c: open the chat's NAM case for the officer's "
              "need or job description, with the materials it names (items: one short name "
              "per material, as SAP would write it). Each material is searched in SAP at once "
              "and counted, by short text and long text. Also updates the need, category or "
              "materials; new=true starts another case.",
              {"need": {"type": "string", "description": "The need in the officer's words"},
               "category": {"type": "string", "enum": list(CATEGORIES)},
               "items": {"type": "array", "items": {"type": "string"},
                         "description": "The materials the need names, one short name each"},
               "new": {"type": "boolean"}}, [],
              lambda **a: s._run("nam_need", s.need, **a)),
        _tool("nam_choose", "PR Creation Flow 1d: which materials go forward. With question= "
              "and no items: asks the officer, the harness putting each material with its SAP "
              "count as an option. With items= (the officer's choice: names, numbers, or 'All "
              "of them'): records it; the items are then worked one at a time, in that order.",
              {"question": {"type": "string"},
               "items": {"type": "array", "items": {"type": "string"}}}, [],
              lambda **a: s._run("nam_choose", s.choose, **a), notify=True),
        _tool("nam_search", "Search SAP again for one item, with other words (its usual name, "
              "a size, a code). Replaces the item's records: once the item is narrowed it "
              "needs restart=true.",
              {"item": ITEM, "query": {"type": "string", "description":
                                       "Search words when they differ from the item's name"},
               "restart": {"type": "boolean", "description":
                           "Search again although the item is already narrowed"}},
              [], lambda **a: s._run("nam_search", s.search, **a)),
        _tool("nam_ask", "PR Creation Flow 1f: ask ONE question that tells the item's remaining "
              "records apart. Each option has a label and the words its records carry, as the "
              "records write them (short or long text); the harness places the records and "
              "counts them, and refuses an option the records do not bear out (fix it and call "
              "again). The officer sees the options as buttons.",
              {"item": ITEM, "question": {"type": "string"},
               "options": {"type": "array", "items": {
                   "type": "object", "properties": {
                       "label": {"type": "string"},
                       "words": {"type": "array", "items": {"type": "string"}}},
                   "required": ["label", "words"]}}},
              ["question", "options"],
              lambda **a: s._run("nam_ask", s.ask, **a), notify=True),
        _tool("nam_answer", "PR Creation Flow 1f-1g: the officer's answer. answer= narrows the "
              "records (an option's label, words such as '0-200', or a material code). field= "
              "and value= record a detail the records do not split on (date needed, location, "
              "use, rating, certificate); default=true with source= when NRL's standard value "
              "is used because the officer does not know.",
              {"item": ITEM, "answer": {"type": "string"}, "field": {"type": "string"},
               "value": {"type": "string"}, "default": {"type": "boolean"},
               "source": {"type": "string"}}, [],
              lambda **a: s._run("nam_answer", s.answer, **a)),
        _tool("nam_pick", "PR Creation Flow 1h: put the item's one material in the cart (its "
              "Key from the records still in), with the quantity and unit; then the next "
              "chosen item comes. remove=true takes the item out of the cart.",
              {"item": ITEM, "key": {"type": "string"}, "quantity": {"type": "number"},
               "unit": {"type": "string"}, "remove": {"type": "boolean"}}, [],
              lambda **a: s._run("nam_pick", s.pick, **a)),
        _tool("nam_tenders", "PR Creation Flow 1j. No item: the PUR cases ranked by how many "
              "of the need's materials each holds (the cart's codes, and the materials not "
              "taken forward), each with its match: the PUR holding the most is 100%. With "
              "item=: that item's past tenders. A PUR's data SAP does not show is "
              "kg_tender_record's.", {"item": ITEM}, [],
              lambda **a: s._run("nam_tenders", s.tenders, **a)),
        _tool("nam_undo", "Take back the officer's last act (an answer, a detail, the choice "
              "of items, a material put in the cart, a PR field), or the last steps= of them. "
              "Each undo goes one further back; a confirmed PR is never taken back.",
              {"steps": {"type": "integer"}}, [],
              lambda **a: s._run("nam_undo", s.undo, **a)),
        _tool("nam_estimate", "Stage 2, only when the officer asks: the cart's estimate. "
              "action: 'build' (last price, 7% a year to the evaluation date, results), 'set' "
              "(a line's quantity or rate), 'decide' (accept or revise a flagged line; revise "
              "with rate=), 'lock' (only when every flag is decided), 'show'.",
              {"action": {"type": "string", "enum": ["build", "set", "decide", "lock", "show"]},
               "line": {"type": "integer"}, "quantity": {"type": "number"},
               "rate": {"type": "number"},
               "decision": {"type": "string", "enum": ["accept", "revise"]},
               "note": {"type": "string"},
               "evaluation_date": {"type": "string", "description": "YYYY-MM-DD; today if "
                                                                    "not given"}}, ["action"],
              lambda **a: s._run("nam_estimate", s.estimate_step, **a)),
        _tool("nam_pr", "Stage 3: one cart item's own PR. action: 'fill' (from stage 1 and "
              "its price), 'set' (the officer's delivery_date, plant, storage_location, "
              "justification; rate= revises the price, accept_price=true accepts a flagged "
              "one), 'confirm' (only on the officer's word, with every mandatory field), "
              "'show'. Then the next item's PR.",
              {"item": ITEM,
               "action": {"type": "string", "enum": ["fill", "set", "confirm", "show"]},
               "delivery_date": {"type": "string"}, "plant": {"type": "string"},
               "storage_location": {"type": "string"}, "justification": {"type": "string"},
               "rate": {"type": "number"}, "accept_price": {"type": "boolean"}},
              ["action"], lambda **a: s._run("nam_pr", s.pr_step, **a)),
        _tool("nam_case", "The chat's NAM case as it stands (materials, chosen items, cart, "
              "records left, answers, PURs, PRs), or case_id= to resume another case here.",
              {"case_id": {"type": "string"}}, [],
              lambda **a: s._run("nam_case", s.show, **a)),
    ]


def reminder(conn, session_id: str) -> tuple[str, dict] | None:
    """(the open question, its options as shown) of the chat's case, for the
    harness to ask again after a turn that asked nothing, or None."""
    data = case.for_session(conn, session_id)
    if data and data.get("choosing"):
        q = data["choosing"]
        return q["question"], {"question": q["question"], "options": q["options"],
                               "field": "nam"}
    it = case.current_item(data) if data else None
    if it is not None and it.get("pending"):
        q = it["pending"]
        return q["question"], {"question": q["question"], "options": narrow.labels(q),
                               "field": "nam"}
    return None
