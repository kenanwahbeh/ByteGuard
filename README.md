<p align="center">
  <img src="assets/logo.png" alt="Byte Balance Technology logo" width="480">
</p>

# **Byte Balance Technology**

# ByteGuard

[العربية](README.ar.md)

ByteGuard sets up a WireGuard VPN server on your own machine with one
command, lets you manage its devices from a web page, and brings the whole
setup back from a single backup file after a server reinstall.

## Install

On a fresh Ubuntu 22.04+ or Debian 12+ server:

```bash
curl -fsSL https://github.com/kenanwahbeh/ByteGuard/releases/latest/download/byteguard.sh -o byteguard.sh
sudo bash byteguard.sh
```

Every release also carries `byteguard.sh.sha256`, and the program is
embedded in the installer as plain text, so you can read it before running
it. Version 1, the old single-file script, stays available as release
[v1.0.0](https://github.com/kenanwahbeh/ByteGuard/releases/tag/v1.0.0);
version 2 does not import its data.

## What it does

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
  `/var/backups/byteguard/` and can also be sent to a Telegram chat and
  uploaded to S3-compatible storage such as Cloudflare R2 each time.

- A web interface in Arabic and English: add and remove devices, show
  their QR codes, see who is connected, switch a device off, make and
  download backups, and connect Telegram. It listens only on the server's
  address inside the VPN, so only connected devices can open it.

- Optionally, the web interface on your own domain through a Cloudflare
  Tunnel, with no port opened. ByteGuard creates a tunnel of its own and
  never touches a cloudflared that is already on the server.

Everything runs on your server and your own accounts. ByteGuard has no
hosted service and collects no data.

## Setup

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
| `sudo byteguard ui setup` | Turn the web interface on and set its password (`ui off` turns it off) |
| `sudo byteguard ui tunnel` | Serve the web interface on your own domain through Cloudflare (`--off` stops it) |
| `sudo byteguard backup` | Make a backup now |
| `sudo byteguard backup telegram` | Send every backup to a Telegram chat through your own bot (`--off` stops it) |
| `sudo byteguard backup s3` | Upload every backup to S3-compatible storage such as Cloudflare R2 (`--off` stops it) |
| `sudo byteguard uninstall` | Remove the VPN, its keys and ByteGuard |

The server's keys and the devices are stored in
`/etc/byteguard/state.json`, readable only by root.
`/etc/wireguard/wg0.conf` is generated from it and should not be edited.

## Web interface

`sudo byteguard ui setup` asks for a password and turns the web interface
on at `http://<server's VPN address>:51821`, for example
`http://10.66.66.1:51821`. Open it from a device that is connected to the
VPN; from anywhere else the address does not answer. The page is in
English or Arabic, and the button in the top corner switches between them.

The interface runs as its own service with a read-only view of the system
apart from ByteGuard's files. Eight wrong passwords from the same address
lock sign-in from that address for five minutes; other addresses, yours
included, are not affected. Running `ui setup` again changes the password and signs everyone
out.

### On your own domain

`sudo byteguard ui tunnel` serves the same page at an address such as
`https://vpn.example.com` through a Cloudflare Tunnel, so you can open it
without being connected to the VPN and without opening a port. It needs a
domain that is in your own Cloudflare account; the free plan is enough.

It asks for the name, checks that the domain is on Cloudflare, installs
`cloudflared` if it is missing, and prints a link. Open the link in a
browser, sign in to Cloudflare and choose the domain. ByteGuard then
creates a tunnel, points the name at it and runs it as
`byteguard-tunnel.service`. The sign-in certificate, which could manage the
whole domain, is deleted straight away; only that one tunnel's credentials
stay on the server.

If the server already runs a Cloudflare tunnel, ByteGuard leaves it alone
and creates a separate one, or tells you the address to point your own
tunnel at if you prefer.

Once it is on a public address, anyone who knows it can reach the sign-in
page. Use a strong password, and consider putting Cloudflare Access in
front of it.

## Backups

Every change (a device added, removed, enabled or disabled, the port
moved) rewrites the backup file in `/var/backups/byteguard/` straight
away. A file on the server does not survive the server being wiped, so
send it somewhere else as well: `sudo byteguard backup telegram` asks for
the token of a bot you create with @BotFather and then delivers every new
backup to your chat.

Backups can also go to any S3-compatible storage: Cloudflare R2, AWS S3,
Backblaze B2 and others. For R2, create a bucket and an API token with
Object Read & Write on that bucket only, then run `sudo byteguard backup s3`
(or use the form in the web interface) with the endpoint
`https://<account id>.r2.cloudflarestorage.com`. A test upload is made
before anything is saved. Each backup is stored under
`byteguard/byteguard-backup-<server>-<time>.sh`, and the newest 10 are
kept. R2 needs a payment method on the Cloudflare account even when usage
stays within the free allowance.

To restore, copy the backup file to a fresh server and run it:

```bash
sudo bash byteguard-backup-NAME.sh
```

Devices reconnect on their own when the new server has the same public
address, or when they were set up with a host name that you point at the
new server. If the address changed, pass `--endpoint NEW_ADDRESS`; every
device then needs its configuration again.

**A backup is not encrypted.** It holds the server's key, every device's
key, the Telegram bot token and the storage keys. Anyone who gets the file can connect to
your VPN, so keep it, and the chat it is sent to, private.

## Security

See [SECURITY.md](SECURITY.md) for what ByteGuard stores, what it exposes
and how to report a vulnerability privately.

## Development

The program is Python 3.10+ and uses only the standard library. To build
the installer from source:

```bash
git clone https://github.com/kenanwahbeh/ByteGuard.git
cd ByteGuard
python3 tools/build.py                  # writes dist/byteguard.sh
sudo bash dist/byteguard.sh
```

```bash
python3 -m unittest discover -s tests   # unit tests, safe to run anywhere
```

Pushing a tag such as `v2.0.1` that matches `byteguard/__init__.py` runs the
tests, builds the installer and publishes it as a GitHub release.

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
