"""Does a model change alter the data in the answers? Run the same questions
through the full agent and record, per question, the tenders (PUR ids) and the
rupee figures the final reply carries.

    # with the model you have now
    .venv/bin/python scripts/llm_consistency.py --save /tmp/model-a.json
    # switch the model (WAKU_MODEL / the dashboard's model menu), run again
    .venv/bin/python scripts/llm_consistency.py --save /tmp/model-b.json
    # what differs between the two
    .venv/bin/python scripts/llm_consistency.py --compare /tmp/model-a.json /tmp/model-b.json

Each run uses a fresh, temporary Waku home, so it never writes to your .waku/
(chat log, memory, cases). It calls your model server and the KG API, nothing
else. The wording of the replies will differ between models; the PUR ids and
the figures should not (waku/nam/answer_data.py adds what a reply leaves out).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import tempfile
import time
from pathlib import Path

QUESTIONS = [
    "Have we bought bimetallic temperature gauges before?",
    "Compare the bimetallic gauge tenders.",
    "Which past tenders involve gaskets?",
    "What rates did we get for spiral wound gaskets?",
    "Have we procured ball valves before?",
]
_PUR = re.compile(r"\bPUR-[A-Z]+-\d+\b")
_RS = re.compile(r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d+)?)")


def facts(reply: str) -> dict:
    return {"pur_ids": sorted(set(_PUR.findall(reply))),
            "rupees": sorted({float(x.replace(",", "")) for x in _RS.findall(reply)}),
            "chars": len(reply)}


def run(questions: list[str]) -> dict:
    from waku.app import Waku
    from waku.config import load_settings

    settings = load_settings()
    home = Path(tempfile.mkdtemp(prefix="waku-consistency-"))
    settings = dataclasses.replace(settings, home=home)
    out = {"model": settings.model, "at": time.strftime("%Y-%m-%d %H:%M"), "answers": []}
    for q in questions:
        agent = Waku(settings)          # a fresh agent per question: no history carries over
        t = time.monotonic()
        result = agent.respond(q)
        reply = result.reply if hasattr(result, "reply") else str(result)
        tools = [c.get("tool") for c in getattr(result, "tool_calls", []) or []]
        row = {"question": q, **facts(reply), "tools": tools,
               "data_added": "Data from the KG" in reply,
               "seconds": round(time.monotonic() - t, 1)}
        out["answers"].append(row)
        print(f"- {q}\n  {len(row['pur_ids'])} tender(s), {len(row['rupees'])} figure(s), "
              f"{row['chars']} chars, tools {tools}"
              f"{', data added by the harness' if row['data_added'] else ''}")
    return out


def compare(a: dict, b: dict) -> int:
    print(f"A: {a['model']} ({a['at']})\nB: {b['model']} ({b['at']})\n")
    same = True
    for qa, qb in zip(a["answers"], b["answers"], strict=False):
        ids_a, ids_b = set(qa["pur_ids"]), set(qb["pur_ids"])
        rs_a, rs_b = set(qa["rupees"]), set(qb["rupees"])
        ok = ids_a == ids_b and rs_a == rs_b
        same &= ok
        print(f"{'SAME' if ok else 'DIFF'}  {qa['question']}")
        if ids_a != ids_b:
            print(f"      tenders only in A: {sorted(ids_a - ids_b)}  only in B: {sorted(ids_b - ids_a)}")
        if rs_a != rs_b:
            print(f"      figures only in A: {sorted(rs_a - rs_b)[:10]}  only in B: {sorted(rs_b - rs_a)[:10]}")
    print("\nThe data matches." if same else "\nThe data differs (see DIFF above).")
    return 0 if same else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--save", help="write the results to this JSON file")
    ap.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"))
    ap.add_argument("--question", action="append", help="ask this instead (repeatable)")
    args = ap.parse_args()
    if args.compare:
        a, b = (json.loads(Path(p).read_text()) for p in args.compare)
        return compare(a, b)
    out = run(args.question or QUESTIONS)
    if args.save:
        Path(args.save).write_text(json.dumps(out, indent=2))
        print(f"saved {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
