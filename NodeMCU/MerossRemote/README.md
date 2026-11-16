# MerossRemote (DOIT.AM ESP8266 NodeMCU)

Breadboard remote: two tactile buttons → HTTP → Mac Meross bridge → ランプ / ファン (`mss110`).

MCU: **ESP8266 NodeMCU** (module text `ESP8266MOD` / `DOIT.AM`) — not ESP32 Amica. Bridge stays on the Mac (`meross/bridge`).

## Wiring (silkscreen)

Bottom-row silk (L→R, photo-confirmed):  
`3V3 GND TX RX D8 D7 D6 D5 GND 3V3 D4 D3 D2 D1 D0`

| Button | Function | Silkscreen | GPIO | Wiring |
|--------|----------|------------|------|--------|
| A | toggle **ランプ** | **D1** | 5 | **D1** ↔ switch ↔ **GND** |
| B | toggle **ファン** | **D2** | 4 | **D2** ↔ switch ↔ **GND** |

- Use `INPUT_PULLUP` — switch other side to **GND**, never 3V3.
- Do **not** use **D3 / D4 / D8** for buttons (boot / flash / onboard LED).
- Power the rail from NodeMCU **3V3** / **GND** (or **VIN** if needed).

## Night-friendly LEDs

Dark-by-default: no idle glow; press flash off unless opted in via `secrets.h`.

| LED | Notes |
|-----|--------|
| Blue onboard (usually **D4** / GPIO2, active-low) | Sketch forces OFF |
| Red power (if present) | Tape if it stays on |

## Flash

1. Arduino IDE + **esp8266** board package (ESP8266 Community).
2. Board: **NodeMCU 1.0 (ESP-12E Module)**.
3. `cp secrets.h.example secrets.h` → Wi‑Fi + Mac bridge IP.
4. Upload `MerossRemote.ino`. Serial 115200: Wi‑Fi IP + `/health` OK.

Bridge first: see `meross/README.md` (`python -m bridge`, port **8787**).
