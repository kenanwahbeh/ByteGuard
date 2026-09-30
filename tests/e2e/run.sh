#!/usr/bin/env bash
# End-to-end check for a disposable machine such as a CI runner.
#
# It installs ByteGuard for real, connects a client from a network namespace,
# drives the device commands and uninstalls again. It changes the firewall
# and the network of the machine it runs on, so never run it on a server
# you care about.
#
#   sudo bash tests/e2e/run.sh dist/byteguard.sh
set -euo pipefail

INSTALLER="${1:?usage: run.sh path/to/byteguard.sh}"
NAMESPACE="bgclient"
HOST_IP="10.200.0.1"
CLIENT_IP="10.200.0.2"
SERVER_VPN_IP="10.66.66.1"
PORT="51820"

step() { printf '\n==> %s\n' "$*"; }
fail() {
  printf 'FAILED: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  ip netns del "$NAMESPACE" 2>/dev/null || true
  ip link del bgveth0 2>/dev/null || true
}
trap cleanup EXIT

# The firewall rules without packet counters, to compare before and after.
firewall_snapshot() {
  iptables-save | grep -v '^#' | sed -E 's/\[[0-9]+:[0-9]+\]//'
}

in_client() { ip netns exec "$NAMESPACE" "$@"; }

# Bring the named device up inside the namespace, replacing any earlier one.
connect_client() {
  local name="$1" conf address
  conf="$(mktemp)"
  byteguard show "$name" --no-qr | grep -vE '^(Address|DNS|MTU) ' >"$conf"
  address="$(byteguard show "$name" --no-qr | awk '$1 == "Address" { print $3 }')"
  ip -n "$NAMESPACE" link del wgc 2>/dev/null || true
  ip -n "$NAMESPACE" link add wgc type wireguard
  in_client wg setconf wgc "$conf"
  rm -f "$conf"
  ip -n "$NAMESPACE" addr add "$address" dev wgc
  ip -n "$NAMESPACE" link set wgc mtu 1420 up
  ip -n "$NAMESPACE" route add default dev wgc
}

# Succeeds once the client can reach the server through the tunnel. A new
# handshake can take a few seconds, so this retries.
reaches_server() {
  for _ in 1 2 3 4 5 6; do
    in_client ping -c 1 -W 2 "$SERVER_VPN_IP" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

before="$(firewall_snapshot)"

step "Install without asking anything"
bash "$INSTALLER" --non-interactive --endpoint "$HOST_IP" --port "$PORT" --first-device phone
wg show wg0 >/dev/null || fail "wg0 is not up after the install"
systemctl is-enabled --quiet wg-quick@wg0 || fail "wg0 would not come back after a reboot"
[[ "$(stat -c %a /etc/byteguard/state.json)" == 600 ]] || fail "the state file is readable by others"
server_key="$(wg show wg0 public-key)"
[[ -n "$(wg show wg0 peers)" ]] || fail "the first device was not applied to the running interface"

step "Connect the first device from a network namespace"
ip netns add "$NAMESPACE"
ip link add bgveth0 type veth peer name bgveth1
ip link set bgveth1 netns "$NAMESPACE"
ip addr add "$HOST_IP/24" dev bgveth0
ip link set bgveth0 up
ip -n "$NAMESPACE" addr add "$CLIENT_IP/24" dev bgveth1
ip -n "$NAMESPACE" link set bgveth1 up
ip -n "$NAMESPACE" link set lo up
connect_client phone
reaches_server || fail "the device cannot reach the server through the tunnel"
byteguard status
byteguard status | grep -E '^phone .* online ' >/dev/null || fail "status does not show the device as online"

step "Reach the internet through the VPN"
in_client curl -sS -m 20 --retry 2 -o /dev/null http://1.1.1.1/ ||
  fail "traffic from the device is not forwarded to the internet"

step "Disable, enable and remove"
byteguard disable phone
reaches_server && fail "a disabled device can still connect"
byteguard enable phone
reaches_server || fail "a re-enabled device cannot connect"
byteguard add laptop >/dev/null
byteguard list
byteguard list | grep -E '^laptop +10\.66\.66\.3$' >/dev/null || fail "the second device did not get the next address"
byteguard remove phone
reaches_server && fail "a removed device can still connect"
connect_client laptop
reaches_server || fail "the second device cannot connect"

step "Run the installer again on a server that is already set up"
bash "$INSTALLER" --non-interactive
[[ "$(wg show wg0 public-key)" == "$server_key" ]] || fail "reinstalling changed the server's key"
byteguard list | grep -E '^laptop ' >/dev/null || fail "reinstalling lost a device"
reaches_server || fail "reinstalling dropped the connection"

step "Back up, wipe the server and restore from the backup file"
byteguard backup
backup_copy="$(mktemp)"
cp /var/backups/byteguard/byteguard-backup-*.sh "$backup_copy"
byteguard uninstall --yes
ip link show wg0 >/dev/null 2>&1 && fail "wg0 survived the uninstall before the restore"
bash "$backup_copy" --yes
rm -f "$backup_copy"
[[ "$(wg show wg0 public-key)" == "$server_key" ]] || fail "the restored server has a different key"
byteguard list | grep -E '^laptop ' >/dev/null || fail "the restore lost a device"
# The device still holds a session with the server that was wiped. WireGuard
# starts a new handshake only after about 15 seconds without an answer.
reaches_server || reaches_server || reaches_server ||
  fail "a device cannot reconnect to the restored server without new settings"

step "Uninstall"
byteguard uninstall --yes
ip link show wg0 >/dev/null 2>&1 && fail "wg0 still exists"
for path in /etc/wireguard/wg0.conf /etc/byteguard /opt/byteguard /usr/local/bin/byteguard; do
  [[ -e $path ]] && fail "$path was left behind"
done
[[ "$(sysctl -n net.ipv4.ip_forward)" == 1 ]] || fail "uninstalling turned forwarding off"
after="$(firewall_snapshot)"
if [[ $before != "$after" ]]; then
  diff <(echo "$before") <(echo "$after") || true
  fail "the firewall is not as it was before the install"
fi

step "All checks passed"
