"""What a chat is in the middle of, kept in state.db so it survives a restart.

One row per chat thread (session_id), with a few named slots:

  case       the NAM case this chat is working on: set when the chat opens a
             case, or when the officer says "resume NAM-2026-0012". It
             outranks "the case this chat touched last" (drive.session_case),
             so starting a second case and going back to the first is exact.
  awaiting   the question the harness asked last in this chat (fill.py), so
             the next message is read as its answer. It used to live in the
             process (Waku._nam_awaiting) and was lost on every restart.
  switch     a new need stated while a case is still going: the officer is
             asked whether to start a new case or carry on, and this holds
             the item until they answer (drive.turn).
  sap        need capture on SAP's lines (WAKU_NAM_SOURCE=sap): the need, the
             materials still in and the open question (sap_need.py).

Nothing here is the case itself: the case lives in nam_cases and the harness
decides everything about it. This is only the chat's place in the flow.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, MutableMapping
from datetime import UTC, datetime

_TABLE = ("CREATE TABLE IF NOT EXISTS nam_chat_state (session_id TEXT NOT NULL, "
          "slot TEXT NOT NULL, value_json TEXT NOT NULL, updated_at TEXT NOT NULL, "
          "PRIMARY KEY (session_id, slot))")
SLOTS = ("case", "awaiting", "switch", "sap")


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute(_TABLE)


def get(conn: sqlite3.Connection, session_id: str, slot: str):
    """The slot's value, or None (no row, no table, or a bad row)."""
    if not session_id:
        return None
    try:
        _ensure(conn)
        row = conn.execute("SELECT value_json FROM nam_chat_state WHERE session_id = ? "
                           "AND slot = ?", (session_id, slot)).fetchone()
        return json.loads(row[0]) if row else None
    except (sqlite3.Error, ValueError):
        return None


def put(conn: sqlite3.Connection, session_id: str, slot: str, value) -> None:
    """Set the slot; None clears it."""
    if slot not in SLOTS:
        raise ValueError(f"no chat slot '{slot}'")
    if not session_id:
        return
    _ensure(conn)
    if value is None:
        conn.execute("DELETE FROM nam_chat_state WHERE session_id = ? AND slot = ?",
                     (session_id, slot))
    else:
        conn.execute("INSERT INTO nam_chat_state (session_id, slot, value_json, updated_at) "
                     "VALUES (?, ?, ?, ?) ON CONFLICT (session_id, slot) DO UPDATE SET "
                     "value_json = excluded.value_json, updated_at = excluded.updated_at",
                     (session_id, slot, json.dumps(value, default=str),
                      datetime.now(UTC).isoformat()))
    conn.commit()


class Awaiting(MutableMapping):
    """The `awaiting` slot of every chat as a {session_id: question} mapping,
    the shape drive.turn takes (tests pass a plain dict)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __getitem__(self, session_id: str):
        value = get(self.conn, session_id, "awaiting")
        if value is None:
            raise KeyError(session_id)
        return value

    def __setitem__(self, session_id: str, value) -> None:
        put(self.conn, session_id, "awaiting", value)

    def __delitem__(self, session_id: str) -> None:
        if get(self.conn, session_id, "awaiting") is None:
            raise KeyError(session_id)
        put(self.conn, session_id, "awaiting", None)

    def __iter__(self) -> Iterator[str]:
        try:
            _ensure(self.conn)
            rows = self.conn.execute("SELECT session_id FROM nam_chat_state WHERE "
                                     "slot = 'awaiting'").fetchall()
        except sqlite3.Error:
            rows = []
        return iter([r[0] for r in rows])

    def __len__(self) -> int:
        return sum(1 for _ in self)


# -- the chat a turn runs in, and what the PR Creation Flow asked in it ----------
#
# Waku sets these for each turn (Waku.respond: enter, then leave); the NAM
# tools read them: the chat whose case they work on (current), the question
# nam_ask or nam_choose showed this turn (asked), and whether the chat has a
# case still being worked (case_open).

from contextvars import ContextVar  # noqa: E402 - kept with what it serves

_CURRENT: ContextVar[str] = ContextVar("nam_chat_session", default="")
# the question nam_ask showed this turn, so a second ask in the same turn
# (the generic ask_options) does not replace its checked options
_ASKED: ContextVar[str] = ContextVar("nam_asked", default="")
# whether the chat has a NAM case still being worked (set per turn by Waku)
_OPEN: ContextVar[bool] = ContextVar("nam_case_open", default=False)


def current() -> str:
    """The chat the running turn belongs to, or ""."""
    return _CURRENT.get()


def enter(session_id: str):
    """Set the turn's chat; returns the token for leave()."""
    return (_CURRENT.set(session_id or ""), _ASKED.set(""), _OPEN.set(False))


def leave(token) -> None:
    current_token, asked_token, open_token = token
    _OPEN.reset(open_token)
    _ASKED.reset(asked_token)
    _CURRENT.reset(current_token)


def set_case_open(value: bool) -> None:
    _OPEN.set(bool(value))


def case_open() -> bool:
    """True while the turn's chat has a NAM case not yet at its PR."""
    return _OPEN.get()


def mark_asked(question: str) -> None:
    _ASKED.set(question)


def asked() -> str:
    """The question nam_ask showed in this turn, or ""."""
    return _ASKED.get()
