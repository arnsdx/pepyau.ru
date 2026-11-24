import hashlib
import os
import sqlite3
import stat
from contextlib import closing
from pathlib import Path, PurePosixPath

SCHEMA = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def open_image(root, relative_path):
    path = PurePosixPath(relative_path)
    if not path.parts or path.is_absolute() or ".." in path.parts:
        raise FileNotFoundError(relative_path)

    candidate = root.joinpath(*path.parts)
    if not candidate.is_relative_to(root) or candidate.is_symlink():
        raise FileNotFoundError(relative_path)
    try:
        resolved = candidate.resolve(strict=True)
    except RuntimeError as error:
        raise FileNotFoundError(relative_path) from error
    if resolved != candidate:
        raise FileNotFoundError(relative_path)

    # O_NONBLOCK prevents a replaced file from blocking open() if it becomes a FIFO.
    flags = os.O_RDONLY
    for option in ("O_BINARY", "O_NOFOLLOW", "O_NONBLOCK"):
        flags |= getattr(os, option, 0)
    descriptor = os.open(candidate, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise FileNotFoundError(relative_path)
        return os.fdopen(descriptor, "rb"), metadata.st_size
    except BaseException:
        os.close(descriptor)
        raise


def content_type(header):
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def raise_walk_error(error):
    raise error


def scan_images(root):
    for directory, subdirs, filenames in os.walk(root, onerror=raise_walk_error):
        directory = Path(directory)
        subdirs[:] = [
            name for name in subdirs
            if not (directory / name).is_symlink() and not (directory / name).is_junction()
        ]
        for filename in filenames:
            candidate = directory / filename
            if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            path = candidate.relative_to(root).as_posix()
            try:
                encoded_path = path.encode("utf-8")
            except UnicodeEncodeError:
                continue
            try:
                image, _ = open_image(root, path)
            except (FileNotFoundError, NotADirectoryError):
                continue
            with image:
                mime = content_type(image.read(12))
            if mime:
                yield hashlib.sha256(encoded_path).hexdigest(), path, mime


def reindex(images_dir, db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path, timeout=30)) as db:
        mode = db.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if mode != "wal":
            raise sqlite3.OperationalError("could not enable WAL mode")
        with db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(SCHEMA)
            db.execute("DELETE FROM images")
            result = db.executemany(
                "INSERT INTO images(id, path, content_type) VALUES (?, ?, ?)",
                scan_images(images_dir),
            )
            return result.rowcount


def lookup(db_path, query, parameters=()):
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute(query, parameters).fetchone()
