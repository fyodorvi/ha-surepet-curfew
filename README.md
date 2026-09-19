# SurePet Curfew for Home Assistant

Custom Home Assistant integration for Sure Petcare flap curfew control. See [SPEC.md](SPEC.md) for the full design.

This repo currently ships a **stub integration** for local development: a demo flap with a lock entity and curfew switch, with no SurePet API calls yet.

## Local test bed

Requirements: Docker and Docker Compose.

```bash
docker compose up -d
```

Open [http://localhost:8123](http://localhost:8123), complete onboarding if this is the first run, then:

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **SurePet Curfew**
3. Enter any username/password and curfew settings (not validated yet)
4. Confirm the **Demo Flap Lock** and **Demo Flap Curfew** entities appear

After changing integration code, restart Home Assistant:

```bash
docker compose restart
```

Stop the test instance:

```bash
docker compose down
```

## Project layout

```
custom_components/surepet_curfew/   # integration source (bind-mounted into HA)
ha-config/                        # HA config dir (runtime state gitignored)
docker-compose.yml                # local HA instance
SPEC.md                           # product spec
```

## Underlying library (planned)

[surepy](https://github.com/benleb/surepy) will be used for Sure Petcare API access in a later iteration.
