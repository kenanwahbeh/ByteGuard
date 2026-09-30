<p align="center">
  <img src="assets/logo.png" alt="Byte Balance Technology logo" width="480">
</p>

# **Byte Balance Technology**

# ByteGuard

ByteGuard sets up a WireGuard VPN server on your own machine with one
command, lets you manage its devices from a web page, and brings the whole
setup back from a single backup file after a server reinstall.

> **Status:** version 2 is in development and has no release yet. The VPN
> server and device management from the terminal work. The web interface
> and backups are not built yet, so for now a server wipe loses the devices.
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

## Still to come

- A web interface in Arabic and English for the same device management,
  with connection status for each device.
- The web interface will never be put on an open port. It will be reached
  through a Cloudflare Tunnel on your own domain, or only from inside the
  VPN.
- A backup after every change, which you can download or have sent to a
  Telegram bot or to S3-compatible storage such as Cloudflare R2. A backup
  will be one runnable file that restores everything on a fresh server. It
  will not be encrypted, so it has to be kept somewhere private.

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
| `sudo byteguard uninstall` | Remove the VPN, its keys and ByteGuard |

The server's keys and the devices are stored in
`/etc/byteguard/state.json`, readable only by root.
`/etc/wireguard/wg0.conf` is generated from it and should not be edited.

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
