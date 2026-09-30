#!/usr/bin/env bash
# ByteGuard installer.
#
# Built by tools/build.py from https://github.com/kenanwahbeh/ByteGuard. The
# program is embedded below as plain text, inside extract_payload, so you can
# read everything this file installs before running it.
#
#   sudo bash byteguard.sh            install and ask the setup questions
#   sudo bash byteguard.sh --help     the options the setup accepts
set -euo pipefail

BYTEGUARD_VERSION="@@BYTEGUARD_VERSION@@"
INSTALL_DIR="/opt/byteguard"
LAUNCHER="/usr/local/bin/byteguard"
STATE_FILE="/etc/byteguard/state.json"
PACKAGES=(wireguard-tools iptables qrencode python3 ca-certificates)

msg() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() {
  printf '\033[1;31merror:\033[0m %s\n' "$*" >&2
  exit 1
}

# @@BYTEGUARD_PAYLOAD@@

check_system() {
  [[ $EUID -eq 0 ]] || die "Run this as root, for example: sudo bash $0"
  declare -F extract_payload >/dev/null ||
    die "This is the unbuilt template. Build the installer with: python3 tools/build.py"
  [[ -r /etc/os-release ]] || die "Cannot tell which system this is: /etc/os-release is missing."
  # shellcheck disable=SC1091
  . /etc/os-release
  local version="${VERSION_ID:-0}"
  local major="${version%%.*}"
  case "${ID:-}" in
    ubuntu) ((major >= 22)) || die "Ubuntu 22.04 or newer is required." ;;
    debian) ((major >= 12)) || die "Debian 12 or newer is required." ;;
    *) die "Only Ubuntu and Debian are supported. This is ${PRETTY_NAME:-an unknown system}." ;;
  esac
  command -v systemctl >/dev/null || die "systemd is required."
}

install_packages() {
  local package missing=()
  for package in "${PACKAGES[@]}"; do
    dpkg -s "$package" >/dev/null 2>&1 || missing+=("$package")
  done
  if ((${#missing[@]})); then
    msg "Installing: ${missing[*]}"
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "${missing[@]}"
  fi
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' ||
    die "Python 3.10 or newer is required."
}

install_program() {
  local staging
  staging="$(mktemp -d)"
  extract_payload "$staging"
  chmod -R u=rwX,go=rX "$staging"
  rm -rf "$INSTALL_DIR"
  mv "$staging" "$INSTALL_DIR"
  cat >"$LAUNCHER" <<EOF
#!/usr/bin/python3
import sys

sys.path.insert(0, "$INSTALL_DIR")
from byteguard.cli import main

sys.exit(main())
EOF
  chmod 755 "$LAUNCHER"
}

usage() {
  cat <<'EOF'
Usage: sudo bash byteguard.sh [setup options]

Installs ByteGuard, then sets this server up as a WireGuard VPN server.
Without options it asks for each setting.

  --iface NAME          network card that faces the internet
  --endpoint ADDRESS    public IP or host name devices connect to
  --port NUMBER         WireGuard UDP port (default 51820)
  --first-device NAME   name of the first device (default phone)
  --non-interactive     ask nothing; use the given values and detect the rest
EOF
}

main() {
  case "${1:-}" in
    -h | --help)
      usage
      return
      ;;
  esac
  check_system
  install_packages
  install_program
  msg "ByteGuard ${BYTEGUARD_VERSION} is installed."
  if [[ -f $STATE_FILE ]]; then
    msg "This server is already set up, so only the program was updated."
    msg "Run 'sudo byteguard' to manage it."
    return
  fi
  exec "$LAUNCHER" setup "$@"
}

main "$@"
