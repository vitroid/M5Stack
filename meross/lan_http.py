#!/usr/bin/env python3
"""Pure LAN HTTP helpers for Meross plugs (no MQTT / no cloud on the command path).

Signing (device message):
  messageId = md5(random16).hexdigest().lower()
  timestamp = unix seconds
  sign      = md5(messageId + key + str(timestamp)).hexdigest().lower()

POST http://{lan_ip}/config  Content-Type: application/json
Body: {"header":{...},"payload":{...}}

Cloud is only used by export_lan_devices.py to obtain key + IPs once.
"""

from __future__ import annotations

import hashlib
import json
import random
import string
import time
from typing import Any, Dict, Optional, Tuple

import urllib.error
import urllib.request

CONTENT_TYPE = "application/json"
DEFAULT_FROM = "http://0.0.0.0/config"


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest().lower()


def build_message(
    *,
    method: str,
    namespace: str,
    payload: Dict[str, Any],
    key: str,
    uuid: str,
    from_addr: str = DEFAULT_FROM,
) -> Tuple[Dict[str, Any], str]:
    randomstring = "".join(
        random.SystemRandom().choice(string.ascii_uppercase + string.digits)
        for _ in range(16)
    )
    message_id = md5_hex(randomstring)
    timestamp = int(round(time.time()))
    sign = md5_hex(f"{message_id}{key}{timestamp}")
    data = {
        "header": {
            "from": from_addr,
            "messageId": message_id,
            "method": method,
            "namespace": namespace,
            "payloadVersion": 1,
            "sign": sign,
            "timestamp": timestamp,
            "triggerSrc": "Android",
            "uuid": uuid,
        },
        "payload": payload,
    }
    return data, message_id


def post_config(
    lan_ip: str,
    message: Dict[str, Any],
    *,
    timeout: float = 3.0,
) -> Tuple[int, Dict[str, Any], float]:
    """POST signed JSON to device /config. Returns (http_status, parsed_json, elapsed_ms)."""
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    url = f"http://{lan_ip}/config"
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": CONTENT_TYPE},
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            status = getattr(resp, "status", 200) or 200
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        raise RuntimeError(f"HTTP {status} from {url}: {raw[:200]}") from exc
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        raise RuntimeError(f"LAN POST failed {url} after {elapsed_ms:.0f}ms: {exc}") from exc
    elapsed_ms = (time.monotonic() - t0) * 1000.0
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON response from {url}: {raw[:200]}") from exc
    return status, parsed, elapsed_ms


def lan_get_all(lan_ip: str, key: str, uuid: str, timeout: float = 3.0) -> Tuple[Dict[str, Any], float]:
    msg, _ = build_message(
        method="GET",
        namespace="Appliance.System.All",
        payload={},
        key=key,
        uuid=uuid,
    )
    _status, parsed, ms = post_config(lan_ip, msg, timeout=timeout)
    return parsed, ms


def lan_set_onoff(
    lan_ip: str,
    key: str,
    uuid: str,
    onoff: int,
    channel: int = 0,
    timeout: float = 3.0,
) -> Tuple[Dict[str, Any], float]:
    msg, _ = build_message(
        method="SET",
        namespace="Appliance.Control.ToggleX",
        payload={"togglex": {"channel": channel, "onoff": int(onoff)}},
        key=key,
        uuid=uuid,
    )
    _status, parsed, ms = post_config(lan_ip, msg, timeout=timeout)
    return parsed, ms


def channel0_on_from_all(parsed: Dict[str, Any]) -> Optional[bool]:
    """Extract channel-0 on/off from Appliance.System.All response."""
    payload = parsed.get("payload") or {}
    digest = (payload.get("all") or {}).get("digest") or {}
    togglex = digest.get("togglex")
    if isinstance(togglex, list):
        for item in togglex:
            if item.get("channel", 0) == 0:
                return bool(item.get("onoff") == 1)
    if isinstance(togglex, dict):
        return bool(togglex.get("onoff") == 1)
    # some firmwares nest under control
    control = (payload.get("all") or {}).get("control") or {}
    toggle = control.get("toggle") or control.get("togglex")
    if isinstance(toggle, dict) and "onoff" in toggle:
        return bool(toggle.get("onoff") == 1)
    return None
