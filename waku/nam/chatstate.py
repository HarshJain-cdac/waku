"""The chat a turn runs in, so a NAM tool knows whose case it works on, and
the question a NAM tool asked in the turn.

Waku sets it for each turn (Waku.respond: enter, then leave); the NAM tools
read it with current(). The case itself, and the chat's place in the flow,
live in the case store (case.py), so a restart loses nothing.
"""

from __future__ import annotations

from contextvars import ContextVar

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
