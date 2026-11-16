"""Optional PlatformIO pre-script: pass Wi‑Fi / Meross macros from the environment.

If WIFI_SSID, WIFI_PASSWORD, MEROSS_KEY, LAMP_IP, … are set in the shell, they
become -D build flags. Prefer a local secrets.h (gitignored) when not using env.
Never commit real credentials.
"""

Import("env")  # noqa: F821 — provided by PlatformIO

import os

for name in (
    "WIFI_SSID",
    "WIFI_PASSWORD",
    "BRIDGE_HOST",
    "BRIDGE_PORT",
    "MEROSS_KEY",
    "MEROSS_CHANNEL",
    "LAMP_IP",
    "LAMP_UUID",
    "FAN_IP",
    "FAN_UUID",
):
    value = os.environ.get(name)
    if value:
        env.Append(CPPDEFINES=[(name, env.StringifyMacro(value))])
