"""Horizon session states and what counts as a completed check-in or check-out.

A Horizon desktop is in one of three states, as the broker sees it:

- ``NO_SESSION`` -- Windows has no logged-on session on the VM;
- ``CONNECTED`` -- a session exists and a client holds an open Blast connection to it;
- ``DISCONNECTED`` -- a session exists and no client is attached (it keeps running).

The accounting system observes the Windows logon and logoff, not the web portal, so
the two rules below speak in these states and nothing else.
"""

# beadloom:domain=domain

from dataclasses import dataclass
from enum import StrEnum


class SessionState(StrEnum):
    """The state of the Windows session behind one Horizon desktop."""

    NO_SESSION = "no_session"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"

    @property
    def has_session(self) -> bool:
        """Whether Windows keeps a logged-on session, attached to a client or not."""
        return self is not SessionState.NO_SESSION


@dataclass(frozen=True)
class DesktopStatus:
    """One desktop tile as the portal reports it: its name and its session state."""

    name: str
    state: SessionState


def checkin_succeeded(while_open: SessionState, after_disconnect: SessionState) -> bool:
    """Whether the morning run logged on and left the session running.

    The check-in is the transition CONNECTED -> DISCONNECTED: the desktop was open over
    Blast (Windows completed the logon), then the client let go without logging off.
    """
    return while_open is SessionState.CONNECTED and after_disconnect is SessionState.DISCONNECTED


def checkout_succeeded(before: SessionState, after: SessionState) -> bool:
    """Whether the evening run logged off a session that existed when it started.

    A desktop that had no session before the run was not logged off by it, so that
    case is not a success; the caller reports it as "already logged off".
    """
    return before.has_session and after is SessionState.NO_SESSION
