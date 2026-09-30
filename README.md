<p align="center">
  <img src="assets/logo.png" alt="Byte Balance Technology logo" width="480">
</p>

# **Byte Balance Technology**

# ByteGuard

ByteGuard sets up a WireGuard VPN server on your own machine with one
command, lets you manage its devices from a web page, and brings the whole
setup back from a single backup file after a server reinstall.

> **Status:** version 2 is being rebuilt from scratch and cannot be
> installed yet. The previous single-file script is still available as
> release [v1.0.0](https://github.com/kenanwahbeh/ByteGuard/releases/tag/v1.0.0).

## What version 2 is being built to do

- Install from one `.sh` file on Ubuntu 22.04+ and Debian 12+.
- Guided setup: it finds the network card that faces the internet and the
  server's public address, confirms both with you, and asks for the port.
- Route all of each device's traffic through the server, with
  `PersistentKeepalive = 25` and `MTU = 1420`.
- A web interface in Arabic and English: add and remove devices, show their
  QR codes, see which ones are connected, and switch a device off without
  deleting it.
- The web interface is never put on an open port. It is reached through a
  Cloudflare Tunnel on your own domain, or only from inside the VPN.
- A backup after every change, which you can download or have sent to a
  Telegram bot or to S3-compatible storage such as Cloudflare R2. A backup
  is one runnable file that restores everything on a fresh server. It is
  not encrypted, so it has to be kept somewhere private.
- Everything runs on your server and your own accounts. ByteGuard has no
  hosted service and collects no data.

## Development

The program is Python 3.10+ and uses only the standard library.

```bash
python3 -m unittest discover -s tests
python3 -m byteguard --version
```

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
