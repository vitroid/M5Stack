# Meross outlet probe + LAN direct + optional HTTP bridge (Python)

Minimal Meross smart-plug control. **Preferred path for MCU remotes: pure LAN HTTP** (no Mac always-on). Cloud login is only for one-shot key/IP export.

- **LAN direct**: `lan_http.py`, `export_lan_devices.py`, `prove_lan_toggle.py`, `gen_nodemcu_secrets.py`
- CLI probe (cloud discovery + LAN-first): `toggle_outlet.py`
- Optional HTTP bridge: `bridge/server.py` (Mac helper / fallback; port 8787)
- Credentials via env only (`env.example`). Never commit secrets (`devices.local.json` is gitignored).

Current remote sketch: [`NodeMCU/MerossRemote`](../NodeMCU/MerossRemote) (ESP8266 NodeMCU) — signs `POST /config` on-device.

## LAN direct (recommended)

```bash
cd meross
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env && $EDITOR .env   # do not commit
set -a && source .env && set +a

python export_lan_devices.py   # writes devices.local.json (key + lan_ip + uuid)
python prove_lan_toggle.py     # pure LAN GET/SET; restores ON; prints latency
python gen_nodemcu_secrets.py  # print #defines for NodeMCU secrets.h
```

Signing: `sign = md5(messageId + key + timestamp)`. Body → `http://{lan_ip}/config`.  
JP protocol notes: iot-bot store `docs/meross-lan-direct.md`.

Note: `meross-iot` 0.4.10.4 LAN path may POST only `messageId` for non-encrypted plugs (library bug); our `lan_http.py` posts the full JSON.

## Quick start (CLI probe)

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

## HTTP bridge (optional Mac fallback)

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
