import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults

from app import create_app
from catalog import MAX_IMAGE_BYTES, RANDOM_IMAGE_SQL, SCHEMA, open_image, reindex


class CatalogSecurityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.images = self.root / "images"
        self.images.mkdir()
        self.db = self.root / "catalog.sqlite3"
        self.image = self.images / "public.jpg"
        self.image.write_bytes(b"\xff\xd8\xffsample")

    def request(self, path):
        app = create_app(self.images, self.db)
        environ = {}
        setup_testing_defaults(environ)
        environ["PATH_INFO"] = path
        statuses = []
        parts = app(environ, lambda status, headers: statuses.append(int(status.split()[0])))
        try:
            return statuses[0], b"".join(parts)
        finally:
            if hasattr(parts, "close"):
                parts.close()

    def test_only_eligible_images_are_indexed_and_served(self):
        (self.images / ".private").mkdir()
        (self.images / ".private" / "picture.jpg").write_bytes(self.image.read_bytes())
        (self.images / ".hidden.jpg").write_bytes(self.image.read_bytes())
        with (self.images / "large.jpg").open("wb") as large:
            large.write(b"\xff\xd8\xff")
            large.truncate(MAX_IMAGE_BYTES + 1)

        self.assertEqual(reindex(self.images, self.db), 1)
        image_id = hashlib.sha256(b"public.jpg").hexdigest()
        self.assertIn(image_id.encode(), self.request("/")[1])
        self.assertEqual(self.request(f"/image/{image_id}"), (200, self.image.read_bytes()))

        # The byte limit also applies if a file changes after indexing.
        with self.image.open("ab") as image:
            image.truncate(MAX_IMAGE_BYTES + 1)
        self.assertEqual(self.request(f"/image/{image_id}")[0], 404)
        status, body = self.request("/api/v2")
        self.assertEqual((status, json.loads(body)), (401, {"code": 401, "error": "Unauthorized"}))

    def test_migration_and_failed_scan_keep_consistent_index(self):
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
            db.execute(SCHEMA)
        self.assertEqual(reindex(self.images, self.db), 1)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "delete")
            previous = db.execute(RANDOM_IMAGE_SQL).fetchone()
            plan = db.execute("EXPLAIN QUERY PLAN " + RANDOM_IMAGE_SQL).fetchall()
            self.assertFalse(any("SCAN images" in row[3] for row in plan), plan)

        with patch("catalog.scan_images", side_effect=OSError("interrupted scan")):
            with self.assertRaises(OSError):
                reindex(self.images, self.db)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute(RANDOM_IMAGE_SQL).fetchone(), previous)

        self.image.unlink()
        self.assertEqual(reindex(self.images, self.db), 0)
        self.assertEqual(self.request("/")[0], 503)

    @unittest.skipUnless(os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"), "dir_fd unavailable")
    def test_open_rejects_link_in_directory_component(self):
        outside = self.root / "other"
        outside.mkdir()
        (outside / "picture.jpg").write_bytes(self.image.read_bytes())
        (self.images / "alias").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(FileNotFoundError):
            open_image(self.images, "alias/picture.jpg")


if __name__ == "__main__":
    unittest.main()
