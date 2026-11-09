"""Who is acting: the trusted identity context, read and checked for shape.

Authentication, user identity and role propagation belong to another
component (D4). It authenticates the caller and passes three values with
every request to Waku (as HTTP headers on the dashboard's chat):

    X-NAM-Tenant   the organisation the caller acts for, e.g. "nrl"
    X-NAM-User     the user id, e.g. "u123"
    X-NAM-Roles    comma-separated roles, e.g. "U1,U3" (or their aliases,
                   "officer,authorized_user"; see policy/permissions.json)

Waku trusts them as given: it never reads a credential and keeps no user
directory. It checks that they are well formed, because every permission
decision (permissions.py) and every case's tenant (case.py) is made from
them. A request without them is the dashboard's own officer (case.LOCAL).
"""

from __future__ import annotations

import re

from waku.nam import case, permissions

_TENANT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_USER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}$")
MAX_ROLES = 10


class BadIdentity(ValueError):
    """The identity context is malformed or incomplete."""


def parse(tenant: str | None, user: str | None, roles: str | None) -> case.Actor:
    tenant, user, roles = (tenant or "").strip(), (user or "").strip(), (roles or "").strip()
    missing = [n for n, v in (("X-NAM-Tenant", tenant), ("X-NAM-User", user),
                              ("X-NAM-Roles", roles)) if not v]
    if missing:
        raise BadIdentity("the identity context is missing " + ", ".join(missing))
    if not _TENANT.match(tenant):
        raise BadIdentity("X-NAM-Tenant is malformed")
    if tenant.lower() == case.LOCAL_TENANT:
        raise BadIdentity(f"X-NAM-Tenant {tenant!r} is reserved")
    if not _USER.match(user):
        raise BadIdentity("X-NAM-User is malformed")
    names = [r.strip() for r in roles.split(",") if r.strip()]
    if not names or len(names) > MAX_ROLES:
        raise BadIdentity(f"X-NAM-Roles must list 1 to {MAX_ROLES} roles")
    canonical: list[str] = []
    for name in names:
        role = permissions.canonical_role(name)
        if role is None:
            raise BadIdentity(f"X-NAM-Roles names an unknown role {name[:20]!r}")
        if role not in canonical:
            canonical.append(role)
    return case.Actor(tenant=tenant, user=user, roles=tuple(canonical))


def from_headers(headers) -> case.Actor | None:
    """The actor a request's headers name, or None when it names none (the
    dashboard's own officer). BadIdentity when they are partial or malformed."""
    values = [headers.get(h) for h in ("X-NAM-Tenant", "X-NAM-User", "X-NAM-Roles")]
    if not any(values):
        return None
    return parse(*values)
