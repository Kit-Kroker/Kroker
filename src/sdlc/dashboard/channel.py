"""The dashboard's Channel adapter (E-10).

The identity-carrying behaviour now lives in channels/contract.py's
ActorChannel, shared with the chat surface (E-86). This subclass exists so
the dashboard's adapter still has a name of its own at its own import path;
it adds nothing and is expected to stay empty.
"""

from __future__ import annotations

from ..channels.contract import ActorChannel


class DashboardChannel(ActorChannel):
    """Channel impl carrying a self-asserted operator identity (OQ-11)."""
