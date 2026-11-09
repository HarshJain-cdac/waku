"""What a caller may do in the PR Creation Flow, enforced in code.

Authentication, user identity and role propagation are another component's
(D4): Waku consumes the identity context it is given (identity.py; for a
turn, case.acting) and checks it here against policy/permissions.json:

  actions   the flow's acts -> the roles that may do them: capture a need
            (stage 1), build and lock the estimate (stage 2), fill and
            confirm the PR (stage 3)

A case belongs to the tenant that opened it (case.py); no other tenant can
read or change it. The matrix is a draft for NRL to correct: who may do what
is an edit to that file, not to code.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

POLICY = Path(__file__).parent / "policy" / "permissions.json"


@lru_cache(maxsize=1)
def policy() -> dict:
    data = json.loads(POLICY.read_text(encoding="utf-8"))
    roles = set(data["roles"])
    for name, allowed in data["actions"].items():
        unknown = set(allowed) - roles
        if unknown:
            raise ValueError(f"permissions.json actions.{name}: unknown roles {unknown}")
    return data


def canonical_role(name: str) -> str | None:
    data = policy()
    if name.upper() in data["roles"]:
        return name.upper()
    return data["aliases"].get(name.lower())


class Forbidden(Exception):
    """The caller's roles do not allow the act."""


def require(roles: tuple[str, ...], action: str) -> None:
    """Forbidden unless one of `roles` may do `action`; an action with no
    entry is allowed to nobody."""
    allowed = list(policy()["actions"].get(action) or [])
    if not set(roles) & set(allowed):
        raise Forbidden(f"'{action}' needs one of the roles {', '.join(allowed) or '(none)'}; "
                        f"the caller has {', '.join(roles) or 'none'}")
