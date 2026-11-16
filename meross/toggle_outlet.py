#!/usr/bin/env python3
"""Minimal Meross plug/outlet probe: list devices and toggle by name or UUID.

Uses albertogeniola/MerossIot (meross-iot). Cloud login is required for
account discovery; commands prefer LAN HTTP when the device reports a LAN IP
(TransportMode.LAN_HTTP_FIRST), with MQTT/cloud as fallback.

Credentials: set MEROSS_EMAIL / MEROSS_PASSWORD (see env.example). Never commit secrets.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Iterable, List, Optional, Sequence, Set

from meross_iot.controller.device import BaseDevice
from meross_iot.controller.mixins.toggle import ToggleMixin, ToggleXMixin
from meross_iot.http_api import MerossHttpClient
from meross_iot.manager import MerossManager, TransportMode

DEFAULT_API_BASE = "https://iotx-ap.meross.com"


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _require_credentials() -> tuple[str, str, str]:
    email = _env("MEROSS_EMAIL")
    password = _env("MEROSS_PASSWORD")
    api_base = _env("MEROSS_API_BASE_URL", DEFAULT_API_BASE)
    if not email or not password:
        print(
            "Missing credentials. Set MEROSS_EMAIL and MEROSS_PASSWORD "
            "(see meross/env.example).",
            file=sys.stderr,
        )
        sys.exit(2)
    assert api_base is not None
    return email, password, api_base


def _is_toggleable(dev: BaseDevice) -> bool:
    return isinstance(dev, (ToggleXMixin, ToggleMixin))


def _collect_toggleables(manager: MerossManager) -> List[BaseDevice]:
    seen: Set[str] = set()
    out: List[BaseDevice] = []
    for cls in (ToggleXMixin, ToggleMixin):
        for dev in manager.find_devices(device_class=cls):
            if dev.uuid in seen:
                continue
            seen.add(dev.uuid)
            out.append(dev)
    # Fallback: any discovered device that happens to expose toggle APIs
    for dev in manager.find_devices():
        if dev.uuid in seen or not _is_toggleable(dev):
            continue
        seen.add(dev.uuid)
        out.append(dev)
    return out


def _match_device(devs: Sequence[BaseDevice], query: str) -> BaseDevice:
    q = query.strip().lower()
    by_uuid = [d for d in devs if d.uuid.lower() == q]
    if by_uuid:
        return by_uuid[0]
    by_name = [d for d in devs if (d.name or "").lower() == q]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        raise SystemExit(
            f"Ambiguous name {query!r}; use UUID. Candidates: "
            + ", ".join(f"{d.name} ({d.uuid})" for d in by_name)
        )
    partial = [d for d in devs if q in (d.name or "").lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise SystemExit(
            f"Ambiguous partial name {query!r}. Candidates: "
            + ", ".join(f"{d.name} ({d.uuid})" for d in partial)
        )
    raise SystemExit(
        f"No device matched {query!r}. Run `list` first. Known: "
        + ", ".join(f"{d.name} ({d.uuid})" for d in devs)
    )


def _lan_ip(dev: BaseDevice) -> str:
    ip = getattr(dev, "lan_ip", None)
    return ip or "-"


def _online(dev: BaseDevice) -> str:
    status = getattr(dev, "online_status", None)
    return str(status) if status is not None else "?"


async def _with_manager(coro_fn):
    email, password, api_base = _require_credentials()
    http_api_client = await MerossHttpClient.async_from_user_password(
        email=email,
        password=password,
        api_base_url=api_base,
    )
    manager = MerossManager(http_client=http_api_client)
    # Prefer same-LAN HTTP; fall back to Meross cloud MQTT automatically.
    manager.default_transport_mode = TransportMode.LAN_HTTP_FIRST
    try:
        await manager.async_init()
        await manager.async_device_discovery()
        return await coro_fn(manager)
    finally:
        manager.close()
        await http_api_client.async_logout()


async def cmd_list(_args: argparse.Namespace) -> None:
    async def run(manager: MerossManager) -> None:
        devs = _collect_toggleables(manager)
        if not devs:
            print("No toggleable Meross plugs/outlets found on this account.")
            return
        # Refresh so lan_ip / online / channel state are populated when possible.
        for d in devs:
            try:
                await d.async_update()
            except Exception as exc:  # noqa: BLE001 — list should continue
                print(f"warn: async_update failed for {d.name!r}: {exc}", file=sys.stderr)
        print(f"{'NAME':<28} {'TYPE':<10} {'ONLINE':<12} {'LAN_IP':<16} ON UUID")
        for d in sorted(devs, key=lambda x: ((x.name or ""), x.uuid)):
            dtype = getattr(d, "type", None) or getattr(d, "device_type", "?")
            on = "-"
            if hasattr(d, "is_on"):
                try:
                    on = str(d.is_on(channel=0))
                except TypeError:
                    on = str(d.is_on())
                except Exception:  # noqa: BLE001
                    on = "?"
            print(
                f"{(d.name or '-'):<28} {str(dtype):<10} {_online(d):<12} "
                f"{_lan_ip(d):<16} {on:<3} {d.uuid}"
            )

    await _with_manager(run)


async def _resolve_target(manager: MerossManager, query: Optional[str]) -> BaseDevice:
    target = query or _env("MEROSS_DEVICE")
    if not target:
        raise SystemExit(
            "Specify a device with --device NAME|UUID or set MEROSS_DEVICE."
        )
    return _match_device(_collect_toggleables(manager), target)


async def _print_status(dev: BaseDevice) -> None:
    await dev.async_update()
    on = None
    if hasattr(dev, "is_on"):
        try:
            on = dev.is_on(channel=0)
        except TypeError:
            on = dev.is_on()
    print(f"name={dev.name!r}")
    print(f"uuid={dev.uuid}")
    print(f"type={getattr(dev, 'type', None) or getattr(dev, 'device_type', '?')}")
    print(f"online={_online(dev)}")
    print(f"lan_ip={_lan_ip(dev)}")
    print(f"channel0_on={on}")
    print("transport=LAN_HTTP_FIRST (falls back to cloud MQTT if LAN fails)")


async def cmd_status(args: argparse.Namespace) -> None:
    async def run(manager: MerossManager) -> None:
        await _print_status(await _resolve_target(manager, args.device))

    await _with_manager(run)


async def cmd_power(args: argparse.Namespace, action: str) -> None:
    async def run(manager: MerossManager) -> None:
        dev = await _resolve_target(manager, args.device)
        await dev.async_update()
        before = None
        if hasattr(dev, "is_on"):
            try:
                before = dev.is_on(channel=0)
            except TypeError:
                before = dev.is_on()

        if action == "on":
            await dev.async_turn_on(channel=0)
        elif action == "off":
            await dev.async_turn_off(channel=0)
        elif action == "toggle":
            if hasattr(dev, "async_toggle"):
                await dev.async_toggle(channel=0)
            else:
                if before:
                    await dev.async_turn_off(channel=0)
                else:
                    await dev.async_turn_on(channel=0)
        else:
            raise SystemExit(f"Unknown action: {action}")

        await asyncio.sleep(0.4)
        await dev.async_update()
        after = None
        if hasattr(dev, "is_on"):
            try:
                after = dev.is_on(channel=0)
            except TypeError:
                after = dev.is_on()
        print(
            f"{action}: {dev.name!r} ({dev.uuid}) "
            f"before={before} after={after} lan_ip={_lan_ip(dev)}"
        )

    await _with_manager(run)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="List / toggle Meross smart plugs via meross-iot "
        "(LAN HTTP preferred, cloud MQTT fallback)."
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List toggleable plugs/outlets on the account")

    def add_device(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--device",
            "-d",
            help="Device name or UUID (default: MEROSS_DEVICE env)",
        )

    for name, help_text in (
        ("status", "Show online / LAN IP / on-off for one device"),
        ("on", "Turn channel 0 on"),
        ("off", "Turn channel 0 off"),
        ("toggle", "Toggle channel 0"),
    ):
        sp = sub.add_parser(name, help=help_text)
        add_device(sp)

    return p


async def async_main(argv: Optional[Iterable[str]] = None) -> None:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if args.command == "list":
        await cmd_list(args)
    elif args.command == "status":
        await cmd_status(args)
    elif args.command in ("on", "off", "toggle"):
        await cmd_power(args, args.command)
    else:
        raise SystemExit(f"Unhandled command: {args.command}")


def main() -> None:
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
