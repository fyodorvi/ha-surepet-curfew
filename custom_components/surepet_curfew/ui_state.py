"""HA-free mapping between desired, observed, and lock entity state."""

from __future__ import annotations

try:
    from .state import FlapSnapshot
except ImportError:
    from state import FlapSnapshot


def entity_is_locked(desired_effective_locked: bool) -> bool:
    """Map controller desired state to LockEntity._attr_is_locked."""
    return desired_effective_locked


def observed_is_locked(snapshot: FlapSnapshot | None) -> bool | None:
    """Return observed lock state from the latest API snapshot."""
    if snapshot is None:
        return None
    return snapshot.effective_locked
