"""Sending backups to S3-compatible storage (Cloudflare R2, AWS S3, Backblaze B2, MinIO...).

Requests are signed with AWS Signature Version 4, written out here so the
program keeps to the standard library.
"""

import datetime
import hashlib
import hmac
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree

from byteguard.errors import ByteGuardError

KEEP = 10
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _hmac(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode(), hashlib.sha256).digest()


def _quote(text: str, safe: str = "~") -> str:
    return urllib.parse.quote(text, safe=safe)


def sign(method: str, url: str, headers: dict, payload_hash: str, access_key: str, secret_key: str,
         region: str, now: datetime.datetime) -> dict:
    """Return `headers` plus the date, content hash and Authorization of a SigV4 request."""
    parts = urllib.parse.urlsplit(url)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    signed_headers = {
        **{name.lower(): str(value).strip() for name, value in headers.items()},
        "host": parts.netloc,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
    }
    names = sorted(signed_headers)
    query = sorted(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    canonical = "\n".join(
        [
            method,
            _quote(parts.path or "/", safe="/~"),
            "&".join(f"{_quote(key)}={_quote(value)}" for key, value in query),
            "".join(f"{name}:{signed_headers[name]}\n" for name in names),
            ";".join(names),
            payload_hash,
        ]
    )
    scope = f"{day}/{region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret_key).encode(), day), region), "s3"), "aws4_request")
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={';'.join(names)}, Signature={signature}"
    )
    return {**headers, "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash, "Authorization": authorization}


class Bucket:
    """One bucket, addressed path-style (endpoint/bucket/key), which every S3-compatible service accepts."""

    def __init__(self, settings: dict, opener=urllib.request.urlopen, clock=None):
        self.settings = settings
        self._opener = opener
        self._clock = clock or (lambda: datetime.datetime.now(datetime.timezone.utc))

    def _url(self, key: str = "", query: str = "") -> str:
        base = self.settings["endpoint"].rstrip("/")
        path = f"/{_quote(self.settings['bucket'])}" + (f"/{_quote(key, safe='/~')}" if key else "")
        return base + path + (f"?{query}" if query else "")

    def _request(self, method: str, url: str, body: bytes = b"", headers: dict | None = None) -> bytes:
        payload_hash = hashlib.sha256(body).hexdigest()
        signed = sign(method, url, headers or {}, payload_hash, self.settings["access_key"],
                      self.settings["secret_key"], self.settings.get("region") or "auto", self._clock())
        request = urllib.request.Request(url, data=body if method == "PUT" else None, method=method, headers=signed)
        try:
            with self._opener(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            code = re.search(rb"<Code>([^<]+)</Code>", error.read() or b"")
            reason = code.group(1).decode() if code else error.reason
            raise ByteGuardError(f"The storage answered with HTTP {error.code} ({reason}).") from None
        except OSError:
            raise ByteGuardError("The storage could not be reached. Check the endpoint address.") from None

    def put(self, key: str, content: bytes) -> None:
        self._request("PUT", self._url(key), content, {"Content-Type": "text/x-shellscript"})

    def keys(self, prefix: str) -> list[str]:
        query = urllib.parse.urlencode({"list-type": "2", "prefix": prefix})
        root = ElementTree.fromstring(self._request("GET", self._url(query=query)))
        return [element.text for element in root.iter() if element.tag.endswith("}Key") or element.tag == "Key"]

    def delete(self, key: str) -> None:
        self._request("DELETE", self._url(key))


def prefix(settings: dict, host: str) -> str:
    return f"{settings.get('folder', 'byteguard').strip('/')}/byteguard-backup-{host}-"


def upload(settings: dict, host: str, content: str, bucket_factory=Bucket, now=None) -> str:
    """Upload a backup under a time-stamped name and keep only the newest KEEP. Returns its key."""
    bucket = bucket_factory(settings)
    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    start = prefix(settings, host)
    key = f"{start}{stamp}.sh"
    bucket.put(key, content.encode())
    # Time-stamped names sort oldest first.
    for old in sorted(bucket.keys(start))[:-KEEP]:
        bucket.delete(old)
    return key
