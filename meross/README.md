# Meross outlet probe (Python)

Minimal cloud+LAN probe for Meross smart plugs/outlets, as a first step toward an M5Stack in-home remote switch.

Repo context: this tree previously had no Meross-specific code. Closest related sketch is [`Atom/AtomSwitch`](../Atom/AtomSwitch) (M5 Atom → local HTTP bridge), which is a useful ESP32 pattern later.

## Quick start

```bash
cd meross
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env   # then edit; do not commit .env
set -a && source .env && set +a

python toggle_outlet.py list
python toggle_outlet.py status --device "Your Plug Name"
python toggle_outlet.py on --device "<uuid-or-name>"
python toggle_outlet.py off --device "<uuid-or-name>"
python toggle_outlet.py toggle --device "<uuid-or-name>"
```

Credentials use env vars only (`MEROSS_EMAIL`, `MEROSS_PASSWORD`, optional `MEROSS_API_BASE_URL`, `MEROSS_DEVICE`). See `env.example`.

Transport: `TransportMode.LAN_HTTP_FIRST` (local HTTP when LAN IP is known; MQTT/cloud fallback). Account discovery still needs Meross cloud login.

Project how-to (Japanese): written under the iot-bot Project store as `docs/meross-python-probe.md` (not in this git tree).
