"""The `byteguard` command."""

import argparse
import datetime
import ipaddress
import sys
from pathlib import Path

from byteguard import __version__, backup, netdetect, telegram, tunnel, wizard
from byteguard.errors import ByteGuardError
from byteguard.manager import DEFAULT_SUBNET, DEFAULT_UI_PORT, Manager, check_subnet
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
    setup.add_argument(
        "--subnet",
        default=DEFAULT_SUBNET,
        help=f"private network for the VPN; the server takes its first address (default {DEFAULT_SUBNET})",
    )
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

    port = commands.add_parser("port", help="move the VPN to another UDP port")
    port.add_argument("number", type=int)
    port.set_defaults(handler=_port)

    ui = commands.add_parser(
        "ui",
        help="web interface: `ui setup` turns it on, `ui off` turns it off, "
        "`ui tunnel` serves it on your own domain through Cloudflare (`ui tunnel --off` stops that)",
    )
    ui.add_argument("action", choices=["setup", "off", "tunnel"])
    ui.add_argument("--hostname", help="with `tunnel`: the name to serve it on, such as vpn.example.com")
    ui.add_argument("--off", action="store_true", help="with `tunnel`: stop serving it through Cloudflare")
    ui.add_argument("--port", type=int, default=DEFAULT_UI_PORT, help=f"port inside the VPN (default {DEFAULT_UI_PORT})")
    ui.add_argument("--password-stdin", action="store_true", help="read the password from standard input")
    ui.set_defaults(handler=_ui)

    # Run by the byteguard-ui service.
    commands.add_parser("serve", help=argparse.SUPPRESS).set_defaults(handler=_serve)

    back_up = commands.add_parser(
        "backup",
        help="make a backup now; `backup telegram` sends every backup to a Telegram chat",
    )
    back_up.add_argument("destination", nargs="?", choices=["telegram"])
    back_up.add_argument("--off", action="store_true", help="stop sending backups to the destination")
    back_up.set_defaults(handler=_backup)

    # Run by a backup file on the server it is restoring.
    restore = commands.add_parser("restore", help=argparse.SUPPRESS)
    restore.add_argument("file", type=Path)
    restore.add_argument("--iface")
    restore.add_argument("--endpoint")
    restore.add_argument("--yes", action="store_true")
    restore.set_defaults(handler=_restore)

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
        code = args.handler(args, manager) or 0
        _warn_about_backup(manager)
        return code
    except ByteGuardError as error:
        print(f"error: {error}", file=sys.stderr)
    except PermissionError:
        print("error: permission denied. Run this with sudo.", file=sys.stderr)
    return 1


def _warn_about_backup(manager: Manager) -> None:
    """Say so when the backup that follows a change did not reach a destination."""
    for destination, result in manager.last_backup.items():
        if not result["ok"]:
            print(f"warning: the {destination} backup failed: {result['error']}", file=sys.stderr)


def _no_command(parser, manager: Manager) -> int:
    if sys.stdin.isatty() and manager.is_set_up():
        return _menu(manager, open_terminal())
    parser.print_help()
    return 0


def _setup(args, manager: Manager) -> None:
    manager.check_can_set_up()
    check_subnet(args.subnet)
    answers = wizard.gather(
        run=manager.run,
        term=None if args.non_interactive else open_terminal(),
        iface=args.iface,
        endpoint=args.endpoint,
        port=args.port,
        first_device=args.first_device,
    )
    manager.set_up(iface=answers.iface, endpoint=answers.endpoint, port=answers.port, subnet=args.subnet)
    print(f"The VPN server is running on {answers.endpoint}, UDP port {answers.port}.")
    manager.add_device(answers.first_device)
    _print_device(manager, answers.first_device, qr=True)
    print("Run `sudo byteguard` to add more devices.")
    if args.non_interactive:
        return
    term = open_terminal()
    if term.confirm("Turn on the web interface? It is reachable only from devices connected to the VPN", default=False):
        _enable_ui(manager, _new_password(term), DEFAULT_UI_PORT)
    else:
        print("You can turn it on later with `sudo byteguard ui setup`.")


def _new_password(term: Terminal) -> str:
    while True:
        password = term.ask_secret("Password for the web interface (8 characters or more)")
        if len(password) < 8:
            term.say("That is too short.")
        elif term.ask_secret("The same password again") != password:
            term.say("The two did not match.")
        else:
            return password


def _enable_ui(manager: Manager, password: str, port: int) -> None:
    address = manager.enable_ui(password, port)
    print(f"The web interface is on: {address}")
    print("Open it from a device that is connected to the VPN.")


def _ui(args, manager: Manager) -> None:
    if args.action == "off":
        manager.disable_ui()
        print("The web interface is off.")
        return
    if args.action == "tunnel":
        _tunnel(args, manager)
        return
    manager.server()
    password = sys.stdin.readline().rstrip("\n") if args.password_stdin else _new_password(open_terminal())
    _enable_ui(manager, password, args.port)


def _tunnel(args, manager: Manager) -> None:
    if args.off:
        settings = manager.tunnel()
        manager.disable_tunnel()
        print("The web interface is no longer served through Cloudflare.")
        if settings:
            print(f"The tunnel {settings['name']} and the DNS record {settings['hostname']} still exist in your")
            print("Cloudflare account. Delete them there if you no longer want them.")
        return
    target = manager.ui_target()
    term = open_terminal()
    run = manager.run

    hostname = args.hostname or term.ask("Name to open the web interface on, such as vpn.example.com")
    if not netdetect.HOSTNAME_RE.fullmatch(hostname):
        raise ByteGuardError(f"{hostname!r} is not a host name.")
    zone, servers = tunnel.zone_of(hostname)
    if not tunnel.on_cloudflare(servers):
        term.say(f"{zone} is not on Cloudflare: its name servers are {', '.join(servers)}.")
        term.say("A tunnel needs the domain in a Cloudflare account, and the free plan is enough:")
        term.say("  1. Add the domain at https://dash.cloudflare.com and check that every DNS record")
        term.say("     was imported. Changing name servers moves the website and email records too.")
        term.say("  2. Set the name servers Cloudflare shows you at the company you bought the domain from.")
        term.say("  3. When Cloudflare says the domain is active, run this command again.")
        raise ByteGuardError("Nothing was changed. The web interface stays reachable from inside the VPN.")

    if tunnel.other_tunnel_running(run):
        term.say("This server already runs a Cloudflare tunnel. ByteGuard will not touch it.")
        if not term.confirm("Create a separate tunnel just for the web interface?"):
            _manual_tunnel(term, hostname, target)
            return
    elif not term.confirm("Let ByteGuard create the tunnel? Answer no to set it up yourself"):
        _manual_tunnel(term, hostname, target)
        return

    if not tunnel.installed(run):
        term.say("Installing cloudflared from Cloudflare's GitHub releases.")
        tunnel.install(run)
    term.say("Open the link below in a browser, sign in to Cloudflare and choose " + zone + ".")
    created = tunnel.create(run, manager.paths.tunnel_dir.with_name("cloudflared-setup"), hostname)
    address = manager.enable_tunnel(hostname, created)
    term.say(f"The web interface is now at {address}")
    term.say("It can take a minute to answer the first time.")
    term.say("Anyone who knows the address can reach the sign-in page, so use a strong password.")


def _manual_tunnel(term: Terminal, hostname: str, target: str) -> None:
    term.say("To set it up yourself, add a public hostname to your tunnel:")
    term.say(f"  hostname: {hostname}")
    term.say(f"  service:  {target}")
    term.say("Nothing was changed on this server.")


def _serve(args, manager: Manager) -> None:
    from byteguard.web import server

    settings = manager.ui()
    if settings is None:
        raise ByteGuardError("The web interface is off. Turn it on with `sudo byteguard ui setup`.")
    httpd = server.make_server(server.App(manager), manager.server()["address"], settings["port"])
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


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


def _port(args, manager: Manager) -> None:
    manager.set_port(args.number)
    print(f"The VPN now listens on UDP port {args.number}.")
    print("Every device needs its configuration again: `sudo byteguard show <name>`.")


def _backup(args, manager: Manager) -> None:
    if args.destination is None:
        results = manager.back_up()
        if results["local"]["ok"]:
            print(f"Backup written to {results['local']['path']}")
        if results.get("telegram", {}).get("ok"):
            print("Backup sent to Telegram.")
        print("The backup is not encrypted and holds every key. Keep it private.")
    elif args.off:
        manager.set_telegram(None)
        print("Backups are no longer sent to Telegram.")
    else:
        _connect_telegram(manager, open_terminal())


def _connect_telegram(manager: Manager, term: Terminal) -> None:
    manager.server()
    term.say("Create a bot with @BotFather in Telegram (/newbot) and paste its token here.")
    token = term.ask("Bot token")
    name = telegram.bot_name(token)
    term.say(f"Now open Telegram and send any message to @{name}.")
    term.ask("Press Enter once it is sent", "done")
    chat = telegram.latest_chat(token)
    if chat is None:
        raise ByteGuardError(f"@{name} has not received a message yet. Send it one and run this again.")
    chat_id, who = chat
    if not term.confirm(f"Send every backup to {who}? It holds all the keys, unencrypted"):
        raise ByteGuardError("Nothing was changed.")
    manager.set_telegram(token, chat_id)
    if manager.last_backup.get("telegram", {}).get("ok"):
        term.say(f"Done. A backup was just sent to {who}, and one will follow every change.")


def _restore(args, manager: Manager) -> None:
    manager.check_can_set_up()
    payload = backup.read_payload(args.file)
    saved = payload["state"]
    cards = netdetect.interfaces(manager.run)
    iface = args.iface or (saved["server"]["iface"] if saved["server"]["iface"] in cards else None)
    iface = iface or netdetect.default_interface(manager.run)
    if iface not in cards:
        raise ByteGuardError("Could not tell which network card faces the internet; pass --iface.")
    endpoint = args.endpoint or saved["server"]["endpoint"]

    count = len(saved["devices"])
    print(f"Backup of {payload['host']}, made {payload['made_at']}: {count} device{'s' if count != 1 else ''}.")
    print(f"It will be restored on network card {iface} ({cards[iface]}), UDP port {saved['server']['port']}.")
    moved = _moved(endpoint, cards)
    if moved:
        print(f"warning: the devices connect to {endpoint}, which is not this server's address.")
        print("They will not reach it unless that address is moved here. To restore with a")
        print("new address, pass --endpoint; every device then needs its configuration again.")
    if not args.yes and not open_terminal().confirm("Restore it on this server?"):
        raise ByteGuardError("Nothing was restored.")
    manager.restore(saved, iface=iface, endpoint=endpoint)
    print("Restored. The VPN is running with the same keys, so devices reconnect on their own.")


def _moved(endpoint: str, cards: dict[str, str]) -> bool:
    """True when the endpoint is an IP address that this server does not have."""
    try:
        ipaddress.ip_address(endpoint)
    except ValueError:
        # A host name: its DNS record decides where it points.
        return False
    return endpoint not in cards.values() and endpoint != netdetect.public_address()


def _uninstall(args, manager: Manager) -> None:
    if not args.yes:
        term = open_terminal()
        term.say("This removes the VPN, every device and the server's keys.")
        term.say("Devices will stop working and cannot be restored afterwards.")
        if not term.confirm("Remove ByteGuard from this server?", default=False):
            raise ByteGuardError("Nothing was removed.")
    manager.uninstall()
    print("ByteGuard was removed from this server.")
    if manager.paths.backups.exists():
        print(f"The last backup was kept in {manager.paths.backups}. It holds every key.")


def _menu(manager: Manager, term: Terminal) -> int:
    actions = [
        ("List devices and who is connected", _menu_status),
        ("Add a device", _menu_add),
        ("Show a device's configuration and QR code", _menu_show),
        ("Enable or disable a device", _menu_toggle),
        ("Remove a device", _menu_remove),
        ("Make a backup now", _menu_backup),
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


def _menu_backup(manager: Manager, term: Terminal) -> None:
    results = manager.back_up()
    for destination, result in results.items():
        term.say(f"{destination}: {result.get('path', 'sent') if result['ok'] else 'failed: ' + result['error']}")


def _menu_remove(manager: Manager, term: Terminal) -> None:
    device = _pick_device(manager, term, "Which device should be removed?")
    if device and term.confirm(f"Remove {device['name']}? It will stop working.", default=False):
        manager.remove_device(device["name"])
        term.say(f"{device['name']} was removed.")
