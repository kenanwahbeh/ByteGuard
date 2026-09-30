# Changelog

## Unreleased

Version 2 is a rewrite from scratch. Nothing from version 1 carries over,
and there is no migration from a version 1 script.

### Removed

- `wireguard-install.sh`, the version 1 installer that stored its state
  inside itself. It is still available in release
  [v1.0.0](https://github.com/kenanwahbeh/ByteGuard/releases/tag/v1.0.0).

### Added

- The installer, `byteguard.sh`, built by `tools/build.py` with the program
  embedded in it as plain text.
- Setup that confirms the network card and the public address and asks for
  the port, with a `--non-interactive` mode.
- The `byteguard` command: `add`, `show`, `list`, `status`, `enable`,
  `disable`, `remove` and `uninstall`, and a menu when run without a command.
- `--subnet` to choose the VPN's private network at setup.
- `byteguard port` to move the VPN to another UDP port after setup.
- Automatic backups: every change rewrites a single runnable backup file
  that restores the whole setup on a fresh server with the same keys.
- `byteguard backup` and `byteguard backup telegram`, which sends every
  backup to a Telegram chat through the user's own bot.
- A web interface in Arabic and English, reachable only from inside the
  VPN: devices, QR codes, connection status, backups and Telegram.
  `byteguard ui setup` turns it on.
- Firewall handling that uses ufw when it is active and iptables otherwise,
  and removes exactly the rules it added.

## 1.0.0 (2026-09-18)

First stable release of the single-file installer.
