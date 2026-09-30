<p align="center">
  <img src="assets/logo.png" alt="Byte Balance Technology logo" width="480">
</p>

# **Byte Balance Technology**

# ByteGuard

ByteGuard sets up a WireGuard VPN server on your own machine with one
command, lets you manage its devices from a web page, and brings the whole
setup back from a single backup file after a server reinstall.

> **Status:** version 2 is in development and has no release yet. The VPN
> server, device management from the terminal and backups work. The web
> interface is not built yet.
> The previous single-file script is still available as release
> [v1.0.0](https://github.com/kenanwahbeh/ByteGuard/releases/tag/v1.0.0).

## What works today

- One installer file for Ubuntu 22.04+ and Debian 12+. The program is
  embedded in it as plain text, so you can read everything it installs.
- Guided setup: it finds the network card that faces the internet and the
  server's public address, confirms both with you, and asks for the port.
- All of each device's traffic goes through the server, with
  `PersistentKeepalive = 25` and `MTU = 1420`.
- Devices are managed from the terminal: add, remove, list, show the QR
  code again at any time, and switch a device off without deleting it.
- It fits in with the firewall that is already there. With ufw active it
  adds ufw rules; without it, it adds iptables rules next to the existing
  ones. It never flushes a chain, and uninstalling removes exactly what it
  added.

- A backup after every change, with nothing to press. The backup is one
  runnable file: run it on a fresh server and the VPN comes back with the
  same keys, so devices reconnect without new settings. It is written to
  `/var/backups/byteguard/` and can also be sent to a Telegram chat each
  time.

## Still to come

- A web interface in Arabic and English for the same device management,
  with connection status for each device.
- The web interface will never be put on an open port. It will be reached
  through a Cloudflare Tunnel on your own domain, or only from inside the
  VPN.
- Sending backups to S3-compatible storage such as Cloudflare R2, and
  downloading them from the web interface.

Everything runs on your server and your own accounts. ByteGuard has no
hosted service and collects no data.

## Trying the development build

```bash
git clone https://github.com/kenanwahbeh/ByteGuard.git
cd ByteGuard
python3 tools/build.py
sudo bash dist/byteguard.sh
```

The installer asks its questions, starts the VPN and prints the first
device's configuration and QR code. To skip the questions, pass
`--non-interactive` with any of `--iface`, `--endpoint`, `--port` and
`--first-device`; whatever is left out is detected.

The VPN uses the private network `10.66.66.0/24` unless you pass another
one, for example `--subnet 10.11.12.0/24`. The server takes the first
address in it and devices get the ones after.

Afterwards, `sudo byteguard` opens a menu. The same actions are commands:

| Command | What it does |
|---|---|
| `sudo byteguard add NAME` | Add a device and show its configuration and QR code |
| `sudo byteguard show NAME` | Show a device's configuration and QR code again |
| `sudo byteguard list` | List the devices |
| `sudo byteguard status` | Show which devices are connected and their traffic |
| `sudo byteguard disable NAME` | Stop a device from connecting without deleting it |
| `sudo byteguard enable NAME` | Let a disabled device connect again |
| `sudo byteguard remove NAME` | Delete a device |
| `sudo byteguard port NUMBER` | Move the VPN to another UDP port; every device then needs its configuration again |
| `sudo byteguard backup` | Make a backup now |
| `sudo byteguard backup telegram` | Send every backup to a Telegram chat through your own bot (`--off` stops it) |
| `sudo byteguard uninstall` | Remove the VPN, its keys and ByteGuard |

The server's keys and the devices are stored in
`/etc/byteguard/state.json`, readable only by root.
`/etc/wireguard/wg0.conf` is generated from it and should not be edited.

## Backups

Every change (a device added, removed, enabled or disabled, the port
moved) rewrites the backup file in `/var/backups/byteguard/` straight
away. A file on the server does not survive the server being wiped, so
send it somewhere else as well: `sudo byteguard backup telegram` asks for
the token of a bot you create with @BotFather and then delivers every new
backup to your chat.

To restore, copy the backup file to a fresh server and run it:

```bash
sudo bash byteguard-backup-NAME.sh
```

Devices reconnect on their own when the new server has the same public
address, or when they were set up with a host name that you point at the
new server. If the address changed, pass `--endpoint NEW_ADDRESS`; every
device then needs its configuration again.

**A backup is not encrypted.** It holds the server's key, every device's
key and the Telegram bot token. Anyone who gets the file can connect to
your VPN, so keep it, and the chat it is sent to, private.

## Development

The program is Python 3.10+ and uses only the standard library.

```bash
python3 -m unittest discover -s tests   # unit tests, safe to run anywhere
python3 tools/build.py                  # builds dist/byteguard.sh
```

`tests/e2e/run.sh` installs for real, connects a client and uninstalls. It
changes the firewall of the machine it runs on, so it is meant for CI
runners and throwaway machines only.

## Sponsor

If this project is useful to you, you can support its development through
Binance Pay: open the Binance app, scan the QR code below, or search for
the nickname **Kinan125**.

<p align="center">
  <img src="assets/binance.jpg" alt="Binance Pay QR code - Kinan125" width="280">
</p>

## License

MIT — see [LICENSE](LICENSE).

WireGuard is a registered trademark of Jason A. Donenfeld. ByteGuard is an
independent project and is not affiliated with or endorsed by the WireGuard
project.
