"""The HTTP server behind the web interface.

It never listens on a public address: it is bound to the server's address
inside the VPN, so only connected devices can reach it.
"""

import base64
import json
import re
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from byteguard import __version__, backup, telegram
from byteguard.errors import ByteGuardError
from byteguard.web import auth

STATIC = Path(__file__).resolve().parent / "static"
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}
COOKIE = "byteguard_session"
MAX_BODY = 64 * 1024
# Browsers cannot add this header to a cross-site form or image request, so
# requiring it on every change stops other sites from acting as the admin.
CSRF_HEADER = "X-ByteGuard"

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

DEVICE = r"(?P<name>[A-Za-z0-9][A-Za-z0-9_-]{0,31})"
ROUTES = [
    ("POST", r"/api/login", "login", False),
    ("POST", r"/api/logout", "logout", True),
    ("GET", r"/api/state", "state", True),
    ("POST", r"/api/devices", "add_device", True),
    ("GET", rf"/api/devices/{DEVICE}", "device", True),
    ("GET", rf"/api/devices/{DEVICE}/config", "device_config", True),
    ("POST", rf"/api/devices/{DEVICE}/(?P<action>enable|disable)", "toggle_device", True),
    ("DELETE", rf"/api/devices/{DEVICE}", "remove_device", True),
    ("POST", r"/api/backup", "back_up", True),
    ("GET", r"/api/backup/download", "download_backup", True),
    ("POST", r"/api/backup/telegram", "connect_telegram", True),
    ("DELETE", r"/api/backup/telegram", "disconnect_telegram", True),
]


class Problem(Exception):
    def __init__(self, status: HTTPStatus, code: str):
        self.status, self.code = status, code


class App:
    """What the handler needs: the manager and the login sessions."""

    def __init__(self, manager, sessions: auth.Sessions | None = None):
        self.manager = manager
        self.sessions = sessions or auth.Sessions()


def make_server(app: App, address: str, port: int) -> ThreadingHTTPServer:
    handler = type("Handler", (Handler,), {"app": app})
    return ThreadingHTTPServer((address, port), handler)


class Handler(BaseHTTPRequestHandler):
    app: App
    server_version = "ByteGuard"
    sys_version = ""

    def log_message(self, format, *args):
        # Keep the journal free of request lines, which include device names.
        pass

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_DELETE(self):
        self._handle("DELETE")

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        try:
            if path.startswith("/api/"):
                self._api(method, path)
            elif method == "GET":
                self._static(path)
            else:
                raise Problem(HTTPStatus.METHOD_NOT_ALLOWED, "method")
        except Problem as problem:
            self._json({"error": problem.code}, problem.status)
        except ByteGuardError as error:
            self._json({"error": "refused", "message": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception:
            # Answer instead of dropping the connection; details stay out of the response.
            self._json({"error": "server"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    # Static files

    def _static(self, path: str) -> None:
        relative = "index.html" if path == "/" else path.lstrip("/")
        target = (STATIC / relative).resolve()
        if STATIC not in target.parents or target.suffix not in STATIC_TYPES or not target.is_file():
            raise Problem(HTTPStatus.NOT_FOUND, "not_found")
        self._send(HTTPStatus.OK, target.read_bytes(), STATIC_TYPES[target.suffix])

    # API

    def _api(self, method: str, path: str) -> None:
        for route_method, pattern, name, needs_login in ROUTES:
            match = re.fullmatch(pattern, path)
            if match and route_method == method:
                break
        else:
            raise Problem(HTTPStatus.NOT_FOUND, "not_found")
        if method != "GET" and self.headers.get(CSRF_HEADER) != "1":
            raise Problem(HTTPStatus.FORBIDDEN, "csrf")
        if needs_login and not self.app.sessions.valid(self._session()):
            raise Problem(HTTPStatus.UNAUTHORIZED, "login")
        getattr(self, f"_{name}")(**match.groupdict())

    def _session(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return cookie[COOKIE].value if COOKIE in cookie else None

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise Problem(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "too_large")
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            raise Problem(HTTPStatus.BAD_REQUEST, "json") from None
        if not isinstance(body, dict):
            raise Problem(HTTPStatus.BAD_REQUEST, "json")
        return body

    def _text(self, body: dict, field: str) -> str:
        value = body.get(field)
        if not isinstance(value, str) or not value:
            raise Problem(HTTPStatus.BAD_REQUEST, "missing")
        return value

    def _login(self) -> None:
        sessions = self.app.sessions
        client = self._client()
        if sessions.locked_out(client):
            raise Problem(HTTPStatus.TOO_MANY_REQUESTS, "locked")
        stored = self.app.manager.ui()
        if stored is None or not auth.verify_password(self._text(self._body(), "password"), stored["password"]):
            sessions.record_failure(client)
            raise Problem(HTTPStatus.UNAUTHORIZED, "password")
        cookie = f"{COOKIE}={sessions.start()}; Path=/; HttpOnly; SameSite=Strict; Max-Age={auth.SESSION_SECONDS}"
        if self.headers.get("X-Forwarded-Proto") == "https":
            # Reached through the tunnel: never send the cookie over plain HTTP.
            cookie += "; Secure"
        self._json({"ok": True}, headers={"Set-Cookie": cookie})

    def _client(self) -> str:
        """Who is signing in, for counting wrong passwords.

        Through the tunnel every request arrives from cloudflared on this same
        address, so there the visitor's address comes from Cloudflare's
        header. Devices in the VPN connect from their own addresses and
        cannot pose as the tunnel.
        """
        peer = self.client_address[0]
        forwarded = self.headers.get("CF-Connecting-IP")
        if forwarded and peer == self.server.server_address[0]:
            return forwarded
        return peer

    def _logout(self) -> None:
        self.app.sessions.end(self._session())
        self._json({"ok": True}, headers={"Set-Cookie": f"{COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"})

    def _state(self) -> None:
        manager = self.app.manager
        server = manager.server()
        chat = manager.telegram_chat()
        try:
            last_backup = json.loads(manager.paths.backup_status.read_text())
        except (OSError, ValueError):
            last_backup = None
        self._json(
            {
                "version": __version__,
                "server": {key: server[key] for key in ("endpoint", "port", "iface", "address")},
                "devices": manager.status(),
                "backup": {"last": last_backup, "telegram": bool(chat)},
            }
        )

    def _device_payload(self, name: str) -> dict:
        manager = self.app.manager
        svg = manager.qr_svg(name)
        return {
            "name": name,
            "config": manager.client_config(name),
            "qr": "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode(),
        }

    def _add_device(self) -> None:
        name = self._text(self._body(), "name")
        self.app.manager.add_device(name)
        self._json(self._device_payload(name), HTTPStatus.CREATED)

    def _device(self, name: str) -> None:
        self._json(self._device_payload(name))

    def _device_config(self, name: str) -> None:
        config = self.app.manager.client_config(name).encode()
        self._send(
            HTTPStatus.OK,
            config,
            "text/plain; charset=utf-8",
            {"Content-Disposition": f'attachment; filename="{name}.conf"'},
        )

    def _toggle_device(self, name: str, action: str) -> None:
        self.app.manager.set_enabled(name, action == "enable")
        self._json({"ok": True})

    def _remove_device(self, name: str) -> None:
        self.app.manager.remove_device(name)
        self._json({"ok": True})

    def _back_up(self) -> None:
        self._json(self.app.manager.back_up())

    def _download_backup(self) -> None:
        text = backup.build(self.app.manager.state_for_backup())
        self._send(
            HTTPStatus.OK,
            text.encode(),
            "text/x-shellscript; charset=utf-8",
            {"Content-Disposition": f'attachment; filename="{backup.file_name()}"'},
        )

    def _connect_telegram(self) -> None:
        """Connect a bot: the chat is the one that last wrote to it."""
        token = self._text(self._body(), "token")
        bot = telegram.bot_name(token)
        chat = telegram.latest_chat(token)
        if chat is None:
            self._json({"connected": False, "bot": bot})
            return
        chat_id, who = chat
        self.app.manager.set_telegram(token, chat_id)
        sent = self.app.manager.last_backup.get("telegram", {})
        self._json({"connected": True, "bot": bot, "chat": who, "sent": sent.get("ok", False)})

    def _disconnect_telegram(self) -> None:
        self.app.manager.set_telegram(None)
        self._json({"ok": True})

    # Responses

    def _json(self, payload, status: HTTPStatus = HTTPStatus.OK, headers: dict | None = None) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json; charset=utf-8", headers)

    def _send(self, status: HTTPStatus, body: bytes, content_type: str, headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in {**SECURITY_HEADERS, **(headers or {})}.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)
