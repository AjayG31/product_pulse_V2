"""Pure incident lifecycle and recurrence decision helpers.

Persistence, authorization, audit writes, detection, and notifications belong to
their separately scoped service tickets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class IncidentStatus(StrEnum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    REOPENED = "REOPENED"


class TransitionResultCode(StrEnum):
    ALLOWED = "TRANSITION_ALLOWED"
    INVALID_STATUS = "INVALID_STATUS"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    STALE_STATE = "STALE_STATE"


@dataclass(frozen=True, slots=True)
class TransitionDecision:
    """A safe result code for a caller to handle or record."""

    allowed: bool
    result_code: TransitionResultCode


_ALLOWED_TRANSITIONS = frozenset(
    {
        (IncidentStatus.NEW, IncidentStatus.ACKNOWLEDGED),
        (IncidentStatus.ACKNOWLEDGED, IncidentStatus.INVESTIGATING),
        (IncidentStatus.INVESTIGATING, IncidentStatus.RESOLVED),
        (IncidentStatus.RESOLVED, IncidentStatus.REOPENED),
        (IncidentStatus.REOPENED, IncidentStatus.INVESTIGATING),
    }
)


def _as_status(value: IncidentStatus | str) -> IncidentStatus | None:
    try:
        return IncidentStatus(value)
    except (TypeError, ValueError):
        return None


def validate_incident_transition(
    *,
    current_status: IncidentStatus | str,
    expected_status: IncidentStatus | str,
    target_status: IncidentStatus | str,
) -> TransitionDecision:
    """Validate an allowed step and reject a stale expected prior state.

    The caller remains responsible for authorization and for applying this
    decision atomically with any required incident event/audit record.
    """

    current = _as_status(current_status)
    expected = _as_status(expected_status)
    target = _as_status(target_status)
    if current is None or expected is None or target is None:
        return TransitionDecision(False, TransitionResultCode.INVALID_STATUS)
    if expected != current:
        return TransitionDecision(False, TransitionResultCode.STALE_STATE)
    if (current, target) not in _ALLOWED_TRANSITIONS:
        return TransitionDecision(False, TransitionResultCode.INVALID_TRANSITION)
    return TransitionDecision(True, TransitionResultCode.ALLOWED)


def is_within_recurrence_window(
    *, resolved_at: datetime, recurrence_at: datetime
) -> bool:
    """Return whether recurrence is at or before 30 elapsed UTC days.

    Naive datetimes and recurrence timestamps before resolution are rejected;
    a false result therefore means the recurrence is later than the boundary.
    """

    if resolved_at.utcoffset() is None or recurrence_at.utcoffset() is None:
        raise ValueError("resolved_at and recurrence_at must be timezone-aware")

    resolved_utc = resolved_at.astimezone(UTC)
    recurrence_utc = recurrence_at.astimezone(UTC)
    elapsed = recurrence_utc - resolved_utc
    if elapsed < timedelta(0):
        raise ValueError("recurrence_at must not precede resolved_at")
    return elapsed <= timedelta(days=30)
