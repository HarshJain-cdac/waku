"""DETERMINISTIC EVAL — the dashboard RESUMES its last recent thread.

Live bug Sean hit: every time the server restarted (which happens a lot during
dev), the chat 'vanished' — _dash_session minted a brand-new dated thread each
process, so the dock loaded empty and the real conversation was parked under the
previous timestamped id. Fix: on startup, resume the most recent dashboard
thread if its last message is still within the idle window; else start fresh."""

from __future__ import annotations

from evals.helpers import ScriptedClient, make_waku
from waku.ops.browser_agent import resume_or_new_session


def _seed(app, session_id, age_minutes, source="dashboard"):
    app.conn.execute(
        "INSERT INTO chat_log (role, content, session_id, created_at, source) "
        "VALUES ('user', 'hi', ?, datetime('now', ?), ?)",
        (session_id, f"-{age_minutes} minutes", source),
    )
    app.conn.commit()


def test_recent_dashboard_thread_is_resumed(tmp_path, monkeypatch):
    monkeypatch.setenv("WAKU_SESSION_IDLE_MINUTES", "60")
    app = make_waku(tmp_path / "home", client=ScriptedClient([]))
    _seed(app, "dashboard-20260101-120000", age_minutes=5)     # fresh
    assert resume_or_new_session(app.conn) == "dashboard-20260101-120000"


def test_idle_thread_is_not_resumed(tmp_path, monkeypatch):
    monkeypatch.setenv("WAKU_SESSION_IDLE_MINUTES", "60")
    app = make_waku(tmp_path / "home", client=ScriptedClient([]))
    _seed(app, "dashboard-20260101-120000", age_minutes=120)   # 2h idle > 60m
    got = resume_or_new_session(app.conn)
    assert got != "dashboard-20260101-120000"
    assert got.startswith("dashboard-")


def test_most_recent_of_several_threads_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("WAKU_SESSION_IDLE_MINUTES", "60")
    app = make_waku(tmp_path / "home", client=ScriptedClient([]))
    _seed(app, "dashboard-20260101-090000", age_minutes=40)
    _seed(app, "dashboard-20260101-100000", age_minutes=10)    # newer
    assert resume_or_new_session(app.conn) == "dashboard-20260101-100000"


def test_only_dashboard_source_threads_are_resumed(tmp_path, monkeypatch):
    """A recent telegram/cli thread must not hijack the dashboard's resume —
    matched by source, not id."""
    monkeypatch.setenv("WAKU_SESSION_IDLE_MINUTES", "60")
    app = make_waku(tmp_path / "home", client=ScriptedClient([]))
    _seed(app, "telegram-12345", age_minutes=1, source="telegram")
    got = resume_or_new_session(app.conn)
    assert got.startswith("dashboard-") and got != "telegram-12345"


def test_new_chat_s_prefixed_thread_is_resumed(tmp_path, monkeypatch):
    """Regression: '+ New chat' creates 's-...' ids. Resuming by source (not a
    'dashboard-%' id filter) means those threads survive a restart too — the bug
    Sean hit where a new chat 'vanished' when the server bounced."""
    monkeypatch.setenv("WAKU_SESSION_IDLE_MINUTES", "60")
    app = make_waku(tmp_path / "home", client=ScriptedClient([]))
    _seed(app, "s-20260101-120000", age_minutes=3, source="dashboard")
    assert resume_or_new_session(app.conn) == "s-20260101-120000"


def test_a_shared_thread_fed_through_the_api_is_resumed(tmp_path, monkeypatch):
    """Live bug, 2026-11-03: the officer's chat reached the shared thread
    through /api/chat (source 'api'); a restart resumed only 'dashboard'
    threads, started an empty one, and the chat lost its open NAM case."""
    monkeypatch.setenv("WAKU_SESSION_IDLE_MINUTES", "60")
    app = make_waku(tmp_path / "home", client=ScriptedClient([]))
    _seed(app, "dashboard-20261103-111409", age_minutes=12, source="api")
    assert resume_or_new_session(app.conn) == "dashboard-20261103-111409"


def test_a_thread_a_client_names_itself_is_not_the_shared_one(tmp_path, monkeypatch):
    monkeypatch.setenv("WAKU_SESSION_IDLE_MINUTES", "60")
    app = make_waku(tmp_path / "home", client=ScriptedClient([]))
    _seed(app, "dashboard-20261103-111409", age_minutes=30, source="api")
    _seed(app, "px-chat-abc", age_minutes=1, source="api")
    assert resume_or_new_session(app.conn) == "dashboard-20261103-111409"
