# Meross outlet probe + HTTP bridge (Python)

Minimal cloud+LAN control for Meross smart plugs/outlets, plus a thin HTTP bridge for MCU remotes.

- CLI probe: `toggle_outlet.py` (`list` / `status` / `on` / `off` / `toggle`)
- HTTP bridge: `bridge/server.py` — long-lived manager; MCU only does GET/POST
- Transport: `TransportMode.LAN_HTTP_FIRST` (local HTTP when reachable; MQTT/cloud fallback)
- Credentials via env only (`env.example`). Never commit secrets.

Closest MCU pattern in-repo: [`Atom/AtomSwitch`](../Atom/AtomSwitch). Current remote sketch: [`NodeMCU/MerossRemote`](../NodeMCU/MerossRemote) (ESP8266 NodeMCU).

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

## HTTP bridge (for NodeMCU / MCU remotes)

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
| GET | `/devices` | Cached list (no per-device update) |
| GET | `/status/lamp` | Cached status |
| GET/POST | `/toggle/lamp` | **202** queued (default, snappy for MCU) |
| GET/POST | `/toggle/fan` | Same |
| GET/POST | `/on/{device}` `/off/{device}` | Same async default |
| GET/POST | `/toggle/lamp?wait=1` | Sync fast path (no rediscovery/update) |
| GET | `/jobs/{id}` | Poll async job |
| | `?device=NAME` | Also works without path segment |

Latency note: per-request discovery/`async_update` used to stall ~10–20s when LAN HTTP failed and MQTT timed out. The bridge now reuses one manager, skips those on power, and returns 202 so ESP is not blocked.

Example from the same LAN:

```bash
curl -s http://127.0.0.1:8787/health
curl -s http://127.0.0.1:8787/devices
curl -s http://127.0.0.1:8787/toggle/lamp
```

Env extras: `MEROSS_BRIDGE_HOST` (default `0.0.0.0`), `MEROSS_BRIDGE_PORT` (default `8787`).

Project how-to (Japanese): iot-bot store `docs/meross-nodemcu-remote.md`.
