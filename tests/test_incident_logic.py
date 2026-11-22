from datetime import UTC, datetime, timedelta, timezone

import pytest

from productpulse.incidents import (
    IncidentStatus,
    TransitionResultCode,
    is_within_recurrence_window,
    validate_incident_transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (IncidentStatus.NEW, IncidentStatus.ACKNOWLEDGED),
        (IncidentStatus.ACKNOWLEDGED, IncidentStatus.INVESTIGATING),
        (IncidentStatus.INVESTIGATING, IncidentStatus.RESOLVED),
        (IncidentStatus.RESOLVED, IncidentStatus.REOPENED),
        (IncidentStatus.REOPENED, IncidentStatus.INVESTIGATING),
    ],
)
def test_approved_incident_transitions_are_allowed(current, target):
    decision = validate_incident_transition(
        current_status=current,
        expected_status=current,
        target_status=target,
    )

    assert decision.allowed is True
    assert decision.result_code is TransitionResultCode.ALLOWED


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (IncidentStatus.NEW, IncidentStatus.INVESTIGATING),
        (IncidentStatus.NEW, IncidentStatus.RESOLVED),
        (IncidentStatus.ACKNOWLEDGED, IncidentStatus.RESOLVED),
        (IncidentStatus.INVESTIGATING, IncidentStatus.ACKNOWLEDGED),
        (IncidentStatus.RESOLVED, IncidentStatus.INVESTIGATING),
        (IncidentStatus.REOPENED, IncidentStatus.RESOLVED),
        (IncidentStatus.NEW, IncidentStatus.NEW),
    ],
)
def test_shortcuts_and_self_transitions_are_rejected(current, target):
    decision = validate_incident_transition(
        current_status=current,
        expected_status=current,
        target_status=target,
    )

    assert decision.allowed is False
    assert decision.result_code is TransitionResultCode.INVALID_TRANSITION


def test_stale_expected_state_is_rejected_with_safe_result_code():
    decision = validate_incident_transition(
        current_status=IncidentStatus.INVESTIGATING,
        expected_status=IncidentStatus.ACKNOWLEDGED,
        target_status=IncidentStatus.RESOLVED,
    )

    assert decision.allowed is False
    assert decision.result_code is TransitionResultCode.STALE_STATE


def test_unknown_status_is_rejected():
    decision = validate_incident_transition(
        current_status="BROKEN",
        expected_status="BROKEN",
        target_status=IncidentStatus.ACKNOWLEDGED,
    )

    assert decision.allowed is False
    assert decision.result_code is TransitionResultCode.INVALID_STATUS


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [
        (timedelta(0), True),
        (timedelta(days=30) - timedelta(microseconds=1), True),
        (timedelta(days=30), True),
        (timedelta(days=30) + timedelta(microseconds=1), False),
        (timedelta(days=31), False),
    ],
)
def test_recurrence_window_uses_inclusive_30_elapsed_days(elapsed, expected):
    resolved_at = datetime(2026, 1, 1, 12, tzinfo=UTC)

    assert is_within_recurrence_window(
        resolved_at=resolved_at,
        recurrence_at=resolved_at + elapsed,
    ) is expected


def test_recurrence_boundary_compares_instants_across_timezones():
    resolved_at = datetime(2026, 1, 1, 7, tzinfo=timezone(timedelta(hours=-5)))
    recurrence_at = datetime(2026, 1, 31, 12, tzinfo=UTC)

    assert is_within_recurrence_window(
        resolved_at=resolved_at,
        recurrence_at=recurrence_at,
    ) is True


@pytest.mark.parametrize(
    ("resolved_at", "recurrence_at"),
    [
        (datetime(2026, 1, 1), datetime(2026, 1, 2, tzinfo=UTC)),
        (datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2)),
    ],
)
def test_recurrence_requires_timezone_aware_timestamps(resolved_at, recurrence_at):
    with pytest.raises(ValueError, match="timezone-aware"):
        is_within_recurrence_window(
            resolved_at=resolved_at,
            recurrence_at=recurrence_at,
        )


def test_recurrence_before_resolution_is_rejected():
    with pytest.raises(ValueError, match="must not precede"):
        is_within_recurrence_window(
            resolved_at=datetime(2026, 1, 2, tzinfo=UTC),
            recurrence_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
