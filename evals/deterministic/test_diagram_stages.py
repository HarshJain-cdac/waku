"""DETERMINISTIC EVAL — the harness diagram shows where a turn IS.

The diagram lit each stage for a fixed 1000ms and then cleared it. On this
deployment a turn spends most of its time waiting on the inference queue at the
LLM stage, so the box you most needed to see was the one it showed least: one
second lit, then a dark diagram for the remaining twenty.

Pinned here:
  * a stage HOLDS until the next one arrives (the CSS always said so — "a node
    holds .hot for as long as it is WORKING, then flashes .done")
  * an empty event queue does not blank the status mid-turn
  * every stage the backend emits has a box to light, and vice versa

Offline: reads the two source files, no browser.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIAGRAM = ROOT / "waku" / "ops" / "static" / "js" / "diagram.js"
STYLE = ROOT / "waku" / "ops" / "static" / "style.css"

pytestmark = pytest.mark.skipif(not DIAGRAM.exists(), reason="static assets not present")


def _source() -> str:
    return DIAGRAM.read_text(encoding="utf-8")


def test_a_stage_is_held_not_flashed():
    source = _source()
    assert "releaseStage" in source, "a stage must be released when the next arrives"
    # the held classes are toggled, not set-then-timed-out
    assert "paint(" in source and "classList.toggle" in source


def test_an_empty_queue_does_not_blank_a_running_turn():
    """Between polls the queue is empty and the turn is still working. Clearing
    there is precisely the moment the diagram should be showing a stage."""
    source = _source()
    body = source[source.index("function playNext"):]
    body = body[: body.index("async function pollEvents")]
    assert 'innerHTML = ""' not in body and "innerHTML=''" not in body


def test_every_emitted_stage_has_a_box():
    """STAGE keys must match what waku actually traces — a mismatch does not
    error, the animation just silently stops lighting things."""
    source = _source()
    block = source[source.index("const STAGE = {"):]
    block = block[: block.index("};")]
    keys = set(re.findall(r"^\s*([a-z_]+):", block, re.MULTILINE))
    assert {"turn_start", "gate", "llm", "tool", "turn_end", "intent", "kg", "nam"} <= keys


def test_stage_node_ids_exist_in_the_drawing():
    """A STAGE entry naming a box that archSVG never draws lights nothing."""
    source = _source()
    drawn = set(re.findall(r'data-node="([a-z_]+)"', source))
    drawn |= set(re.findall(r'"","([a-z_]+)"\)', source))  # box(...) trailing id
    block = source[source.index("const STAGE = {"):]
    block = block[: block.index("};")]
    for node in set(re.findall(r'nodes:\[([^\]]*)\]', block)):
        for name in re.findall(r'"([a-z_]+)"', node):
            assert name in drawn, f'STAGE lights "{name}" but archSVG never draws it'


def test_the_css_contract_the_js_now_keeps():
    assert ".arch .node.done" in STYLE.read_text(encoding="utf-8")


def test_stage_edge_ids_exist_in_the_drawing():
    """turn_start once lit "e-gw-wm", an edge the chart never drew (the
    gateway reaches working memory through the intent node), so the first
    stage of every turn lit no arrow."""
    source = _source()
    drawn = set(re.findall(r'data-edge="([a-z0-9-]+)"', source))
    drawn |= set(re.findall(r'"(?:dash)?","(e-[a-z0-9-]+)"\)', source))   # flow(...) trailing id
    block = source[source.index("const STAGE = {"):]
    block = block[: block.index("};")]
    for edges in re.findall(r'edges:\[([^\]]*)\]', block):
        for name in re.findall(r'"([a-z0-9-]+)"', edges):
            assert name in drawn, f'STAGE lights edge "{name}" but archSVG never draws it'


def test_the_chart_draws_the_real_blocks():
    """knowledge.md describes the architecture; the chart must not leave out a
    block the code has, nor claim the harness runs on a laptop."""
    source = _source()
    for node in ("gateway", "intent", "wm", "llm", "tools", "model", "reply", "kg",
                 "nam", "gate", "procedural", "semantic", "episodic", "consolidation", "trace"):
        assert f'"{node}"' in source, node
    assert "runs on your laptop" not in source and "off this machine" not in source
    assert "waku/tools/kg_precedent.py" not in source      # moved to waku/nam/kg_tools.py
