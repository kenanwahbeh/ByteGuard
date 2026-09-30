# Changelog

## Unreleased

Version 2 is a rewrite from scratch. Nothing from version 1 carries over,
and there is no migration from a version 1 script.

### Removed

- `wireguard-install.sh`, the version 1 installer that stored its state
  inside itself. It is still available in release
  [v1.0.0](https://github.com/kenanwahbeh/ByteGuard/releases/tag/v1.0.0).

### Added

- The `byteguard` Python package, with only `--version` so far.

## 1.0.0 (2026-09-18)

First stable release of the single-file installer.
