"""Optional PlatformIO pre-script: pass Wi‑Fi / bridge macros from the environment.

If WIFI_SSID, WIFI_PASSWORD, and/or BRIDGE_HOST are set in the shell, they become
-D build flags. Prefer a local secrets.h (gitignored) when not using env.
Never commit real credentials.
"""

Import("env")  # noqa: F821 — provided by PlatformIO

import os

for name in ("WIFI_SSID", "WIFI_PASSWORD", "BRIDGE_HOST", "BRIDGE_PORT"):
    value = os.environ.get(name)
    if value:
        env.Append(CPPDEFINES=[(name, env.StringifyMacro(value))])
