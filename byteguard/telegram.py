"""Sending backup files to a Telegram chat through a bot."""

import json
import urllib.error
import urllib.request
import uuid

from byteguard.errors import ByteGuardError

API = "https://api.telegram.org"


def _call(token: str, method: str, body: bytes | None = None, content_type: str | None = None, opener=urllib.request.urlopen):
    request = urllib.request.Request(f"{API}/bot{token}/{method}", data=body)
    if content_type:
        request.add_header("Content-Type", content_type)
    try:
        with opener(request, timeout=30) as response:
            answer = json.loads(response.read())
    except urllib.error.HTTPError as error:
        # The URL holds the bot token, so only the status is reported.
        hint = " The bot token was rejected." if error.code in (401, 404) else ""
        raise ByteGuardError(f"Telegram answered with HTTP {error.code}.{hint}") from None
    except (OSError, ValueError):
        raise ByteGuardError("Telegram could not be reached.") from None
    if not answer.get("ok"):
        raise ByteGuardError(f"Telegram refused the request: {answer.get('description', 'no reason given')}")
    return answer["result"]


def send_document(token: str, chat_id: int, filename: str, content: str, caption: str, opener=urllib.request.urlopen) -> None:
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (("chat_id", str(chat_id)), ("caption", caption)):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n')
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\n'
        f"Content-Type: text/plain\r\n\r\n{content}\r\n--{boundary}--\r\n"
    )
    _call(token, "sendDocument", "".join(parts).encode(), f"multipart/form-data; boundary={boundary}", opener)


def bot_name(token: str, opener=urllib.request.urlopen) -> str:
    return _call(token, "getMe", opener=opener)["username"]


def latest_chat(token: str, opener=urllib.request.urlopen) -> tuple[int, str] | None:
    """The chat of the most recent message sent to the bot, as (id, who)."""
    for update in reversed(_call(token, "getUpdates", opener=opener)):
        chat = update.get("message", {}).get("chat")
        if chat:
            who = chat.get("username") or chat.get("title") or chat.get("first_name") or str(chat["id"])
            return chat["id"], who
    return None
