"""The administrator's password and login sessions."""

import hashlib
import hmac
import secrets
import time

SESSION_SECONDS = 12 * 60 * 60
# After this many wrong passwords, logins are refused until the window passes.
MAX_FAILURES = 8
FAILURE_WINDOW_SECONDS = 5 * 60
MIN_PASSWORD_LENGTH = 8

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> dict:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return {"salt": salt.hex(), "hash": digest.hex(), **_SCRYPT}


def verify_password(password: str, stored: dict) -> bool:
    digest = hashlib.scrypt(
        password.encode(),
        salt=bytes.fromhex(stored["salt"]),
        dklen=32,
        n=stored["n"],
        r=stored["r"],
        p=stored["p"],
    )
    return hmac.compare_digest(digest, bytes.fromhex(stored["hash"]))


class Sessions:
    """Login sessions and the brake on password guessing. Both live in memory only."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._sessions: dict[str, float] = {}
        self._failures: list[float] = []

    def locked_out(self) -> bool:
        cutoff = self._clock() - FAILURE_WINDOW_SECONDS
        self._failures = [moment for moment in self._failures if moment > cutoff]
        return len(self._failures) >= MAX_FAILURES

    def record_failure(self) -> None:
        self._failures.append(self._clock())

    def start(self) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = self._clock() + SESSION_SECONDS
        return token

    def valid(self, token: str | None) -> bool:
        expiry = self._sessions.get(token or "")
        if expiry is None:
            return False
        if expiry < self._clock():
            del self._sessions[token]
            return False
        return True

    def end(self, token: str | None) -> None:
        self._sessions.pop(token or "", None)

    def end_all(self) -> None:
        self._sessions.clear()
