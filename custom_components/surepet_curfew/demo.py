"""In-memory demo flap used until surepy integration is wired up."""

from __future__ import annotations

from dataclasses import dataclass

from .const import DEMO_FLAP_NAME


@dataclass
class DemoFlap:
    """Stub flap state for local development."""

    name: str = DEMO_FLAP_NAME
    locked: bool = False
    curfew_enabled: bool = True
