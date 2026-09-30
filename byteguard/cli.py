"""The `byteguard` command."""

import argparse
import datetime
import sys

from byteguard import __version__, wizard
from byteguard.errors import ByteGuardError
from byteguard.manager import Manager
from byteguard.paths import INTERFACE
from byteguard.prompt import Terminal, open_terminal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="byteguard",
        description="Install and manage a WireGuard server.",
    )
    parser.add_argument("--version", action="version", version=f"byteguard {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="command")

    setup = commands.add_parser("setup", help="set this server up as a VPN server")
    setup.add_argument("--iface", help="network card that faces the internet")
    setup.add_argument("--endpoint", help="public IP or host name devices connect to")
    setup.add_argument("--port", type=int, help=f"WireGuard UDP port (default {wizard.DEFAULT_PORT})")
    setup.add_argument("--first-device", help=f"name of the first device (default {wizard.DEFAULT_DEVICE})")
    setup.add_argument(
        "--non-interactive",
        action="store_true",
        help="ask nothing; use the given values and detect the rest",
    )
    setup.set_defaults(handler=_setup)

    commands.add_parser("list", help="list the devices").set_defaults(handler=_list)
    commands.add_parser("status", help="show which devices are connected").set_defaults(handler=_status)

    add = commands.add_parser("add", help="add a device and show its configuration")
    add.add_argument("name")
    add.set_defaults(handler=_add)

    show = commands.add_parser("show", help="show a device's configuration and QR code")
    show.add_argument("name")
    show.add_argument("--no-qr", action="store_true", help="print the configuration only")
    show.set_defaults(handler=_show)

    for command, enabled, text in (
        ("enable", True, "let a disabled device connect again"),
        ("disable", False, "stop a device from connecting without deleting it"),
    ):
        toggle = commands.add_parser(command, help=text)
        toggle.add_argument("name")
        toggle.set_defaults(handler=_toggle, enabled=enabled)

    remove = commands.add_parser("remove", help="delete a device")
    remove.add_argument("name")
    remove.set_defaults(handler=_remove)

    uninstall = commands.add_parser("uninstall", help="remove the VPN, its keys and ByteGuard")
    uninstall.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    uninstall.set_defaults(handler=_uninstall)
    return parser


def main(argv: list[str] | None = None, manager: Manager | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    manager = manager or Manager()
    try:
        if args.command is None:
            return _no_command(parser, manager)
        return args.handler(args, manager) or 0
    except ByteGuardError as error:
        print(f"error: {error}", file=sys.stderr)
    except PermissionError:
        print("error: permission denied. Run this with sudo.", file=sys.stderr)
    return 1


def _no_command(parser, manager: Manager) -> int:
    if sys.stdin.isatty() and manager.is_set_up():
        return _menu(manager, open_terminal())
    parser.print_help()
    return 0


def _setup(args, manager: Manager) -> None:
    manager.check_can_set_up()
    answers = wizard.gather(
        run=manager.run,
        term=None if args.non_interactive else open_terminal(),
        iface=args.iface,
        endpoint=args.endpoint,
        port=args.port,
        first_device=args.first_device,
    )
    manager.set_up(iface=answers.iface, endpoint=answers.endpoint, port=answers.port)
    print(f"The VPN server is running on {answers.endpoint}, UDP port {answers.port}.")
    manager.add_device(answers.first_device)
    _print_device(manager, answers.first_device, qr=True)
    print("Run `sudo byteguard` to add more devices.")


def _list(args, manager: Manager) -> None:
    devices = manager.devices()
    if not devices:
        print("No devices yet. Add one with `sudo byteguard add <name>`.")
        return
    for device in devices:
        state = "" if device["enabled"] else "  (disabled)"
        print(f"{device['name']:<32}  {device['address']}{state}")


def _status(args, manager: Manager) -> None:
    for device in manager.status():
        print(_status_line(device))


def _status_line(device: dict) -> str:
    if not device["enabled"]:
        state = "disabled"
    elif device["online"]:
        state = "online"
    elif device["last_handshake"]:
        seen = datetime.datetime.fromtimestamp(device["last_handshake"])
        state = f"last seen {seen:%Y-%m-%d %H:%M}"
    else:
        state = "never connected"
    traffic = f"received {_size(device['received'])}, sent {_size(device['sent'])}"
    return f"{device['name']:<32}  {device['address']:<15}  {state:<28}  {traffic}"


def _size(count: int) -> str:
    size = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def _add(args, manager: Manager) -> None:
    manager.add_device(args.name)
    _print_device(manager, args.name, qr=True)


def _show(args, manager: Manager) -> None:
    _print_device(manager, args.name, qr=not args.no_qr)


def _print_device(manager: Manager, name: str, *, qr: bool) -> None:
    print(manager.client_config(name), end="")
    if qr:
        print()
        print(manager.qr_code(name), end="")
        print(f"Scan this code with the WireGuard app to connect {name}.")


def _toggle(args, manager: Manager) -> None:
    manager.set_enabled(args.name, args.enabled)
    print(f"{args.name} is now {'enabled' if args.enabled else 'disabled'}.")


def _remove(args, manager: Manager) -> None:
    manager.remove_device(args.name)
    print(f"{args.name} was removed.")


def _uninstall(args, manager: Manager) -> None:
    if not args.yes:
        term = open_terminal()
        term.say("This removes the VPN, every device and the server's keys.")
        term.say("Devices will stop working and cannot be restored afterwards.")
        if not term.confirm("Remove ByteGuard from this server?", default=False):
            raise ByteGuardError("Nothing was removed.")
    manager.uninstall()
    print("ByteGuard was removed from this server.")


def _menu(manager: Manager, term: Terminal) -> int:
    actions = [
        ("List devices and who is connected", _menu_status),
        ("Add a device", _menu_add),
        ("Show a device's configuration and QR code", _menu_show),
        ("Enable or disable a device", _menu_toggle),
        ("Remove a device", _menu_remove),
        ("Quit", None),
    ]
    while True:
        server = manager.server()
        term.say()
        term.say(
            f"ByteGuard {__version__}: {INTERFACE} on {server['iface']}, "
            f"{server['endpoint']} UDP port {server['port']}"
        )
        _, action = actions[term.choose("What would you like to do?", [label for label, _ in actions])]
        if action is None:
            return 0
        try:
            action(manager, term)
        except ByteGuardError as error:
            term.say(f"error: {error}")


def _pick_device(manager: Manager, term: Terminal, question: str) -> dict | None:
    devices = manager.devices()
    if not devices:
        term.say("There are no devices yet.")
        return None
    labels = [f"{d['name']}{'' if d['enabled'] else ' (disabled)'}" for d in devices]
    return devices[term.choose(question, labels)]


def _menu_status(manager: Manager, term: Terminal) -> None:
    lines = [_status_line(device) for device in manager.status()]
    term.say("\n".join(lines) if lines else "There are no devices yet.")


def _menu_add(manager: Manager, term: Terminal) -> None:
    name = term.ask("Name for the new device")
    manager.add_device(name)
    term.say(manager.client_config(name))
    term.say(manager.qr_code(name))


def _menu_show(manager: Manager, term: Terminal) -> None:
    device = _pick_device(manager, term, "Which device?")
    if device:
        term.say(manager.client_config(device["name"]))
        term.say(manager.qr_code(device["name"]))


def _menu_toggle(manager: Manager, term: Terminal) -> None:
    device = _pick_device(manager, term, "Which device?")
    if device:
        manager.set_enabled(device["name"], not device["enabled"])
        term.say(f"{device['name']} is now {'disabled' if device['enabled'] else 'enabled'}.")


def _menu_remove(manager: Manager, term: Terminal) -> None:
    device = _pick_device(manager, term, "Which device should be removed?")
    if device and term.confirm(f"Remove {device['name']}? It will stop working.", default=False):
        manager.remove_device(device["name"])
        term.say(f"{device['name']} was removed.")
