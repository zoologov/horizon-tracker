"""Unit tests for the Horizon session states and the check-in/check-out success rules."""

import dataclasses

import pytest

from horizon_tracker.domain.session import (
    DesktopStatus,
    SessionState,
    checkin_succeeded,
    checkout_succeeded,
)

NO_SESSION = SessionState.NO_SESSION
CONNECTED = SessionState.CONNECTED
DISCONNECTED = SessionState.DISCONNECTED


# --- SessionState -----------------------------------------------------------


def test_session_state_has_exactly_the_three_horizon_states() -> None:
    assert {state.name for state in SessionState} == {"NO_SESSION", "CONNECTED", "DISCONNECTED"}


@pytest.mark.parametrize(
    ("state", "expected"),
    [(NO_SESSION, False), (CONNECTED, True), (DISCONNECTED, True)],
)
def test_has_session_is_true_while_windows_keeps_a_logged_on_session(
    state: SessionState, expected: bool
) -> None:
    assert state.has_session is expected


# --- DesktopStatus ----------------------------------------------------------


def test_desktop_status_names_the_desktop_and_its_state() -> None:
    status = DesktopStatus(name="DEV desktop", state=DISCONNECTED)

    assert status.name == "DEV desktop"
    assert status.state is DISCONNECTED


def test_desktop_status_is_immutable() -> None:
    status = DesktopStatus(name="DEV desktop", state=CONNECTED)

    with pytest.raises(dataclasses.FrozenInstanceError):
        status.state = NO_SESSION  # type: ignore[misc]  # asserting the frozen dataclass rejects it


# --- check-in: connected while open, disconnected after the client let go ----


def test_checkin_succeeds_when_the_desktop_connected_and_the_client_then_disconnected() -> None:
    assert checkin_succeeded(CONNECTED, DISCONNECTED) is True


@pytest.mark.parametrize("while_open", [NO_SESSION, DISCONNECTED])
def test_checkin_fails_when_the_desktop_never_connected(while_open: SessionState) -> None:
    assert checkin_succeeded(while_open, DISCONNECTED) is False


def test_checkin_fails_when_leaving_logged_windows_off() -> None:
    assert checkin_succeeded(CONNECTED, NO_SESSION) is False


def test_checkin_fails_when_the_client_never_let_go() -> None:
    assert checkin_succeeded(CONNECTED, CONNECTED) is False


# --- check-out: a session existed before, none exists after -----------------


@pytest.mark.parametrize("before", [CONNECTED, DISCONNECTED])
def test_checkout_succeeds_when_a_session_existed_and_none_remains(before: SessionState) -> None:
    assert checkout_succeeded(before, NO_SESSION) is True


@pytest.mark.parametrize("after", [CONNECTED, DISCONNECTED])
@pytest.mark.parametrize("before", [CONNECTED, DISCONNECTED])
def test_checkout_fails_while_a_session_remains(before: SessionState, after: SessionState) -> None:
    assert checkout_succeeded(before, after) is False


def test_checkout_of_a_desktop_already_logged_off_is_not_a_success() -> None:
    # Nothing was logged off by this run: the evening run reports "already out" instead.
    assert checkout_succeeded(NO_SESSION, NO_SESSION) is False
