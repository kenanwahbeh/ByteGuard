import datetime
import io
import unittest
import urllib.error

from byteguard import s3
from byteguard.errors import ByteGuardError
from byteguard.manager import Manager
from fakes import FakeRun, temp_paths

SETTINGS = {
    "endpoint": "https://account.r2.cloudflarestorage.com",
    "bucket": "backups",
    "access_key": "AKID",
    "secret_key": "SECRET-KEY",
    "region": "auto",
    "folder": "byteguard",
}
NOW = datetime.datetime(2026, 9, 30, 12, 0, tzinfo=datetime.timezone.utc)


class SignatureTest(unittest.TestCase):
    def test_it_matches_the_example_aws_publishes(self):
        # "Example: GET Object" from the AWS Signature Version 4 documentation for S3.
        headers = s3.sign(
            "GET", "https://examplebucket.s3.amazonaws.com/test.txt", {"Range": "bytes=0-9"}, s3.EMPTY_SHA256,
            "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1",
            datetime.datetime(2013, 5, 24, tzinfo=datetime.timezone.utc),
        )

        self.assertTrue(headers["Authorization"].endswith(
            "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"))
        self.assertIn("SignedHeaders=host;range;x-amz-content-sha256;x-amz-date", headers["Authorization"])

    def test_the_secret_key_never_appears_in_the_headers(self):
        headers = s3.sign("PUT", "https://x.example/b/k", {}, s3.EMPTY_SHA256, "AKID", "SECRET-KEY", "auto", NOW)

        self.assertNotIn("SECRET-KEY", repr(headers))


class Opener:
    def __init__(self, answers=None, error=None):
        self.requests, self.answers, self.error = [], list(answers or []), error

    def __call__(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        return io.BytesIO(self.answers.pop(0) if self.answers else b"")


class BucketTest(unittest.TestCase):
    def test_an_upload_is_a_signed_path_style_put_of_the_file(self):
        opener = Opener()

        s3.Bucket(SETTINGS, opener, lambda: NOW).put("byteguard/b.sh", b"#!/bin/bash\n")

        (request,) = opener.requests
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.full_url, "https://account.r2.cloudflarestorage.com/backups/byteguard/b.sh")
        self.assertEqual(request.data, b"#!/bin/bash\n")
        self.assertTrue(request.get_header("Authorization").startswith("AWS4-HMAC-SHA256 Credential=AKID/20260930/auto/s3/"))

    def test_listing_reads_the_keys_from_the_xml_answer(self):
        answer = (b'<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                  b"<Contents><Key>byteguard/a.sh</Key></Contents><Contents><Key>byteguard/b.sh</Key></Contents>"
                  b"</ListBucketResult>")

        keys = s3.Bucket(SETTINGS, Opener([answer]), lambda: NOW).keys("byteguard/")

        self.assertEqual(keys, ["byteguard/a.sh", "byteguard/b.sh"])

    def test_a_refusal_names_the_storage_error_but_never_the_secret(self):
        body = io.BytesIO(b"<Error><Code>InvalidAccessKeyId</Code></Error>")
        error = urllib.error.HTTPError("https://x", 403, "Forbidden", {}, body)

        with self.assertRaises(ByteGuardError) as raised:
            s3.Bucket(SETTINGS, Opener(error=error), lambda: NOW).put("k", b"x")

        self.assertIn("InvalidAccessKeyId", str(raised.exception))
        self.assertNotIn("SECRET-KEY", str(raised.exception))


class FakeBucket:
    def __init__(self, existing=()):
        self.objects = dict.fromkeys(existing, b"old")

    def __call__(self, settings):
        return self

    def put(self, key, content):
        self.objects[key] = content

    def keys(self, prefix):
        return [key for key in self.objects if key.startswith(prefix)]

    def delete(self, key):
        del self.objects[key]


class UploadTest(unittest.TestCase):
    def test_each_backup_gets_a_time_stamped_name(self):
        bucket = FakeBucket()

        key = s3.upload(SETTINGS, "vps", "backup", bucket, NOW)

        self.assertEqual(key, "byteguard/byteguard-backup-vps-20260930T120000Z.sh")
        self.assertEqual(bucket.objects[key], b"backup")

    def test_only_the_newest_ten_are_kept_and_other_files_are_left_alone(self):
        old = [f"byteguard/byteguard-backup-vps-202609{day:02d}T000000Z.sh" for day in range(1, 13)]
        bucket = FakeBucket([*old, "byteguard/notes.txt", "byteguard/byteguard-backup-other-20260901T000000Z.sh"])

        s3.upload(SETTINGS, "vps", "backup", bucket, NOW)

        mine = sorted(key for key in bucket.objects if key.startswith("byteguard/byteguard-backup-vps-"))
        self.assertEqual(len(mine), s3.KEEP)
        self.assertEqual(mine[-1], "byteguard/byteguard-backup-vps-20260930T120000Z.sh")
        self.assertIn("byteguard/notes.txt", bucket.objects)
        self.assertIn("byteguard/byteguard-backup-other-20260901T000000Z.sh", bucket.objects)


class ManagerS3Test(unittest.TestCase):
    def manager(self, upload):
        manager = Manager(temp_paths(self), FakeRun(), upload=upload)
        manager.set_up(iface="eth0", endpoint="203.0.113.7", port=51820)
        return manager

    def test_every_change_is_uploaded_once_a_bucket_is_set(self):
        uploads = []
        manager = self.manager(lambda settings, host, text: uploads.append(text) or "key")
        manager.set_s3(SETTINGS)

        manager.add_device("phone")

        self.assertEqual(len(uploads), 2)
        self.assertIn('"name": "phone"', uploads[-1])
        self.assertEqual(manager.last_backup["s3"], {"ok": True, "key": "key"})

    def test_a_failed_upload_is_reported_without_undoing_the_change(self):
        def upload(settings, host, text):
            raise ByteGuardError("The storage could not be reached.")

        manager = self.manager(upload)
        manager.set_s3(SETTINGS)
        manager.add_device("phone")

        self.assertEqual(len(manager.devices()), 1)
        self.assertFalse(manager.last_backup["s3"]["ok"])

    def test_turning_it_off_stops_the_uploads(self):
        uploads = []
        manager = self.manager(lambda settings, host, text: uploads.append(text) or "key")
        manager.set_s3(SETTINGS)
        manager.set_s3(None)
        before = len(uploads)

        manager.add_device("phone")

        self.assertEqual(len(uploads), before)
        self.assertIsNone(manager.s3_settings())


if __name__ == "__main__":
    unittest.main()
