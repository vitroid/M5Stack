# MerossRemote (DOIT.AM ESP8266 NodeMCU) — LAN direct

Breadboard remote: two tactile buttons → **signed HTTP POST** → Meross **ランプ** / **ファン** (`mss110`) on the home LAN.

**No Mac required for day-to-day toggles.** Account `key` + device LAN IP/uuid live in `include/secrets.h` (gitignored). Optional Mac `meross/bridge` is fallback / future key-refresh only.

MCU: **ESP8266 NodeMCU** (module text `ESP8266MOD` / `DOIT.AM`) — not ESP32 Amica.

Flash with **PlatformIO only** (no Arduino IDE).

## Wiring (silkscreen)

Bottom-row silk (L→R, photo-confirmed):  
`3V3 GND TX RX D8 D7 D6 D5 GND 3V3 D4 D3 D2 D1 D0`

| Button | Function | Silkscreen | GPIO | Wiring |
|--------|----------|------------|------|--------|
| A | toggle **ランプ** | **D1** | 5 | **D1** ↔ switch ↔ **GND** |
| B | toggle **ファン** | **D2** | 4 | **D2** ↔ switch ↔ **GND** |

- Use `INPUT_PULLUP` — switch other side to **GND**, never 3V3.
- Do **not** use **D3 / D4 / D8** for buttons (boot / flash / onboard LED).

## Night-friendly LEDs

Dark-by-default: no idle glow; press flash off unless opted in via `secrets.h`.

## One-shot key export (Mac, occasional)

```bash
cd meross
source .venv/bin/activate
set -a && source .env && set +a   # MEROSS_EMAIL / MEROSS_PASSWORD — never commit
python export_lan_devices.py      # → devices.local.json (gitignored)
python prove_lan_toggle.py        # optional pure-LAN proof; restores ON
python gen_nodemcu_secrets.py     # print #define block for secrets.h
```

Paste the printed `MEROSS_KEY` / `LAMP_*` / `FAN_*` into `include/secrets.h` together with Wi‑Fi.

## Flash (PlatformIO)

```bash
cd NodeMCU/MerossRemote
cp secrets.h.example include/secrets.h   # then fill Wi‑Fi + LAN macros
pio run -t upload
pio device monitor -b 115200
```

Board envs: `nodemcuv2` (default) or `esp12e`.

Boot log should show `MerossRemote LAN-direct boot`, NTP OK, and `boot lamp/fan on=…` from LAN GET (no SET). Buttons toggle via `POST http://{ip}/config`.

If a signed request fails, the sketch clears its key-valid flag and hits the Mac refresh stub (currently `/health` only) — re-run `export_lan_devices.py` and update `secrets.h`.

Protocol notes (JP): iot-bot store `docs/meross-lan-direct.md`.
