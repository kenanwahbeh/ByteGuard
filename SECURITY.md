# Security

## Reporting a vulnerability

Please report it privately through GitHub: open the repository's
**Security** tab and choose **Report a vulnerability**. Do not open a
public issue for it. You will get an answer, and a fix will be released
before the details are made public.

## What ByteGuard stores

Everything lives on your own server:

- `/etc/byteguard/state.json`, readable only by root, holds the server's
  WireGuard key, every device's key and preshared key, the web interface's
  password hash (scrypt), and the credentials of the backup destinations
  and of the web interface's Cloudflare tunnel.
- `/etc/wireguard/wg0.conf` is generated from it.

Device keys are kept on purpose, so a device's QR code can be shown again.

## Backups are not encrypted

A backup is the installer with that state inside it, in plain text. It is
written to `/var/backups/byteguard/` (root only) and, if you set them up,
sent to your Telegram chat and uploaded to your S3-compatible bucket.
Anyone who gets a backup can connect to your VPN and can use the bot token
and storage keys inside it. Keep the chat and the bucket private.

## What is exposed

- **WireGuard** listens on the UDP port you chose.
- **The web interface** listens only on the server's address inside the
  VPN, and the firewall rule that admits it names the VPN interface, so it
  does not answer on a public address.
- **With `byteguard ui tunnel`** the sign-in page is reachable by anyone who
  knows the address. Wrong passwords are limited per visitor, but a strong
  password matters, and Cloudflare Access in front of it adds a second
  gate.
- The web interface service keeps a single capability (managing network
  interfaces) and sees the system read-only apart from ByteGuard's own
  directories.

## What ByteGuard changes on the server

It adds firewall rules next to the existing ones and removes exactly those
on uninstall; it never flushes a chain or changes a policy. It never turns
IP forwarding off, because other software such as Docker may rely on it.
It never touches a WireGuard setup or a Cloudflare tunnel it did not
create.

ByteGuard has no hosted service and sends nothing anywhere except to the
backup destinations you configure.
