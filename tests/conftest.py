"""Shared pytest fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "surepet_curfew"
# Import HA-free modules directly (avoid loading __init__.py).
if str(COMPONENT) not in sys.path:
    sys.path.insert(0, str(COMPONENT))


@pytest.fixture
def pet_door_unlocked() -> dict:
    return json.loads((Path(__file__).parent / "fixtures" / "pet_door_unlocked.json").read_text())


@pytest.fixture
def credentials_path() -> Path:
    return ROOT / ".credentials"


@pytest.fixture
def has_credentials(credentials_path: Path) -> bool:
    if not credentials_path.exists():
        return False
    lines = [line.strip() for line in credentials_path.read_text().splitlines() if line.strip()]
    return len(lines) >= 2
