"""State machines for ``jobs.status`` and ``applications.status`` (spec §6).

Illegal transitions raise :class:`IllegalTransition`. The dicts are the single
source of truth; the CLI and pipeline call :func:`assert_transition` before
writing a status.
"""

from __future__ import annotations

from typing import Final


class IllegalTransition(Exception):
    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"illegal transition: {current!r} -> {target!r}")


# jobs.status: new | parsed | rejected | shortlisted | composed | gated_fail
#               | queued | approved | sent | closed
#               | delivered | applied | skipped   (Telegram MVP, decision 0014)
JOB_STATUSES: Final[tuple[str, ...]] = (
    "new",
    "parsed",
    "rejected",
    "shortlisted",
    "composed",
    "gated_fail",
    "queued",
    "approved",
    "sent",
    "closed",
    "delivered",
    "applied",
    "skipped",
)

JOB_ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "new": frozenset({"parsed", "rejected"}),
    "parsed": frozenset({"shortlisted", "rejected"}),
    "shortlisted": frozenset({"composed", "rejected"}),
    "composed": frozenset({"queued", "gated_fail", "rejected"}),
    "gated_fail": frozenset({"composed", "rejected"}),  # regenerate or give up
    "queued": frozenset({"approved", "delivered", "rejected"}),
    "approved": frozenset({"sent", "rejected"}),
    "sent": frozenset({"closed"}),
    "delivered": frozenset({"applied", "skipped", "closed"}),
    "applied": frozenset({"closed"}),
    "skipped": frozenset({"closed"}),
    "rejected": frozenset(),
    "closed": frozenset(),
}


# applications.status: queued | approved | sent | replied | screen | interview
#                      | offer | accepted | rejected | ghosted | withdrawn
APPLICATION_STATUSES: Final[tuple[str, ...]] = (
    "queued",
    "approved",
    "sent",
    "replied",
    "screen",
    "interview",
    "offer",
    "accepted",
    "rejected",
    "ghosted",
    "withdrawn",
)

APPLICATION_ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "queued": frozenset({"approved"}),
    "approved": frozenset({"sent"}),
    "sent": frozenset({"replied", "ghosted", "withdrawn"}),
    "replied": frozenset({"screen", "interview", "offer", "rejected", "withdrawn"}),
    "screen": frozenset({"interview", "offer", "rejected", "withdrawn"}),
    "interview": frozenset({"offer", "rejected", "withdrawn"}),
    "offer": frozenset({"accepted", "rejected", "withdrawn"}),
    "accepted": frozenset(),
    "rejected": frozenset(),
    "ghosted": frozenset(),
    "withdrawn": frozenset(),
}


def assert_transition(
    current: str, target: str, *, kind: str = "application"
) -> None:
    """Raise :class:`IllegalTransition` if ``current -> target`` is not allowed."""
    if kind == "job":
        table = JOB_ALLOWED_TRANSITIONS
    elif kind == "application":
        table = APPLICATION_ALLOWED_TRANSITIONS
    else:
        raise ValueError(f"unknown state-machine kind: {kind!r}")
    allowed = table.get(current, frozenset())
    if target not in allowed:
        raise IllegalTransition(current, target)
