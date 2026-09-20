#!/usr/bin/env python3
"""Read-only probe of Sure Petcare API for Pet Door Connect."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import aiohttp
from surepy import Surepy
from surepy.const import BASE_RESOURCE, MESTART_RESOURCE
from surepy.enums import EntityType

PET_DOOR_PRODUCT_ID = EntityType.PET_FLAP.value  # 3


def load_credentials(path: Path) -> tuple[str, str]:
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    if len(lines) < 2:
        raise SystemExit(f"Expected email and password in {path}")
    return lines[0], lines[1]


async def main() -> None:
    cred_path = Path(__file__).resolve().parents[1] / ".credentials"
    email, password = load_credentials(cred_path)

    async with aiohttp.ClientSession() as session:
        surepy = Surepy(email=email, password=password, session=session)
        await surepy.sac.get_token()

        me = await surepy.sac.call("GET", MESTART_RESOURCE)
        households = (me or {}).get("data", {}).get("households", [])
        print("=== Households ===")
        for hh in households:
            print(json.dumps(hh, indent=2, default=str))

        entities = await surepy.get_entities(refresh=True)
        pet_doors = [
            e for e in entities.values() if e.type == EntityType.PET_FLAP
        ]
        cat_flaps = [
            e for e in entities.values() if e.type == EntityType.CAT_FLAP
        ]

        print(f"\n=== Pet Doors: {len(pet_doors)}, Cat Flaps: {len(cat_flaps)} ===")

        for door in pet_doors:
            raw = door.raw_data()
            print(f"\n--- Pet Door: {door.name} (id={door.id}) ---")
            print("control:", json.dumps(raw.get("control"), indent=2, default=str))
            print("status:", json.dumps(raw.get("status"), indent=2, default=str))

            household_id = door.household_id
            timeline_url = (
                f"{BASE_RESOURCE}/timeline/household/{household_id}"
                "?page=1&page_size=25"
            )
            timeline = await surepy.sac.call("GET", timeline_url)
            events = (timeline or {}).get("data", [])
            lock_events = [e for e in events if e.get("type") in (6, 20)]
            print(f"timeline lock/curfew events (types 6,20): {len(lock_events)}")
            for event in lock_events[:5]:
                print(json.dumps(event, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
