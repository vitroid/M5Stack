# Meross outlet probe + HTTP bridge (Python)

Minimal cloud+LAN control for Meross smart plugs/outlets, plus a thin HTTP bridge for ESP32 / Amica remotes.

- CLI probe: `toggle_outlet.py` (`list` / `status` / `on` / `off` / `toggle`)
- HTTP bridge: `bridge/server.py` — long-lived manager; MCU only does GET/POST
- Transport: `TransportMode.LAN_HTTP_FIRST` (local HTTP when reachable; MQTT/cloud fallback)
- Credentials via env only (`env.example`). Never commit secrets.

Closest MCU pattern in-repo: [`Atom/AtomSwitch`](../Atom/AtomSwitch). Amica sketch: [`Amica/MerossRemote`](../Amica/MerossRemote).

## Quick start (CLI)

```bash
cd meross
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env   # then edit; do not commit .env
set -a && source .env && set +a

python toggle_outlet.py list
python toggle_outlet.py status --device "ランプ"
python toggle_outlet.py toggle --device "ファン"
```

## HTTP bridge (for Amica)

```bash
cd meross
source .venv/bin/activate
set -a && source .env && set +a
# optional: export MEROSS_BRIDGE_HOST=0.0.0.0 MEROSS_BRIDGE_PORT=8787
python -m bridge
# or: python bridge/server.py
```

Home aliases: `lamp` / `ランプ`, `fan` / `ファン`.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | Liveness (no Meross call) |
| GET | `/devices` | List toggleable plugs |
| GET | `/status/lamp` | Status for ランプ |
| GET/POST | `/toggle/lamp` | Toggle ランプ |
| GET/POST | `/toggle/fan` | Toggle ファン |
| GET/POST | `/on/{device}` `/off/{device}` | Explicit on/off |
| | `?device=NAME` | Also works without path segment |

Example from the same LAN:

```bash
curl -s http://127.0.0.1:8787/health
curl -s http://127.0.0.1:8787/devices
curl -s http://127.0.0.1:8787/toggle/lamp
```

Env extras: `MEROSS_BRIDGE_HOST` (default `0.0.0.0`), `MEROSS_BRIDGE_PORT` (default `8787`).

Project how-to (Japanese): iot-bot store `docs/meross-amica-remote.md`.
