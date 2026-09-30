import io
import json
import unittest
import urllib.error

from byteguard import telegram
from byteguard.errors import ByteGuardError


class Opener:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.requests = answer, error, []

    def __call__(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        return io.BytesIO(json.dumps(self.answer).encode())


class SendDocumentTest(unittest.TestCase):
    def test_the_file_goes_to_the_chat_as_a_document(self):
        opener = Opener({"ok": True, "result": {}})

        telegram.send_document("TOKEN", 42, "backup.sh", "#!/bin/bash\necho hi\n", "note", opener)

        (request,) = opener.requests
        body = request.data.decode()
        self.assertEqual(request.full_url, "https://api.telegram.org/botTOKEN/sendDocument")
        self.assertIn('name="chat_id"\r\n\r\n42\r\n', body)
        self.assertIn('name="document"; filename="backup.sh"', body)
        self.assertIn("#!/bin/bash\necho hi\n", body)

    def test_a_refusal_from_telegram_gives_its_reason(self):
        opener = Opener({"ok": False, "description": "chat not found"})

        with self.assertRaisesRegex(ByteGuardError, "chat not found"):
            telegram.send_document("TOKEN", 42, "backup.sh", "x", "note", opener)

    def test_errors_never_repeat_the_bot_token(self):
        failures = (
            urllib.error.HTTPError("https://api.telegram.org/botTOKEN/sendDocument", 401, "Unauthorized", {}, None),
            urllib.error.URLError("unreachable https://api.telegram.org/botTOKEN/"),
        )
        for failure in failures:
            with self.subTest(failure=failure), self.assertRaises(ByteGuardError) as raised:
                telegram.send_document("TOKEN", 42, "backup.sh", "x", "note", Opener(error=failure))
            self.assertNotIn("TOKEN", str(raised.exception))


class LatestChatTest(unittest.TestCase):
    def test_the_newest_message_decides_the_chat(self):
        updates = [
            {"message": {"chat": {"id": 1, "first_name": "Old"}}},
            {"edited_message": {}},
            {"message": {"chat": {"id": 2, "username": "kinan"}}},
        ]

        self.assertEqual(telegram.latest_chat("TOKEN", Opener({"ok": True, "result": updates})), (2, "kinan"))

    def test_a_bot_nobody_wrote_to_has_no_chat(self):
        self.assertIsNone(telegram.latest_chat("TOKEN", Opener({"ok": True, "result": []})))


if __name__ == "__main__":
    unittest.main()
