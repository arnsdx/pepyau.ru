import errno
import hashlib
import os
import sqlite3
import stat
from contextlib import closing
from pathlib import Path, PurePosixPath

SCHEMA = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
RANDOM_IMAGE_SQL = """
    SELECT id FROM images
    WHERE rowid = 1 + abs(random() % (SELECT max(rowid) FROM images))
"""


def open_from_directory(root, parts, flags):
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(root, directory_flags)
    try:
        for part in parts[:-1]:
            child = os.open(part, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        return os.open(parts[-1], flags | os.O_NOFOLLOW, dir_fd=directory)
    finally:
        os.close(directory)


def open_local_path(root, parts, flags):
    # Windows does not support dir_fd. Use this path with a trusted local writer.
    candidate = root.joinpath(*parts)
    if not candidate.is_relative_to(root) or candidate.is_symlink():
        raise FileNotFoundError(candidate)
    try:
        resolved = candidate.resolve(strict=True)
    except RuntimeError as error:
        raise FileNotFoundError(candidate) from error
    if resolved != candidate:
        raise FileNotFoundError(candidate)
    return os.open(candidate, flags)


def open_image(root, relative_path):
    path = PurePosixPath(relative_path)
    if not path.parts or path.is_absolute() or any(part.startswith(".") for part in path.parts):
        raise FileNotFoundError(relative_path)

    # Avoid blocking if a file is replaced with a FIFO before open().
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
            descriptor = open_from_directory(root, path.parts, flags)
        else:
            descriptor = open_local_path(root, path.parts, flags)
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise FileNotFoundError(relative_path) from error
        raise

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_IMAGE_BYTES:
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
            if not name.startswith(".")
            and not (directory / name).is_symlink()
            and not (directory / name).is_junction()
        ]
        for filename in filenames:
            candidate = directory / filename
            if filename.startswith(".") or candidate.suffix.lower() not in IMAGE_EXTENSIONS:
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
        mode = db.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
        if mode != "delete":
            raise sqlite3.OperationalError("could not enable rollback journal")
        with db:
            db.execute("BEGIN IMMEDIATE")
            # Scan under the writer reservation, before modifying the live index.
            images = list(scan_images(images_dir))
            db.execute(SCHEMA)
            db.execute("DELETE FROM images")
            db.executemany(
                "INSERT INTO images(rowid, id, path, content_type) VALUES (?, ?, ?, ?)",
                ((rowid, *image) for rowid, image in enumerate(images, 1)),
            )
    return len(images)


def lookup(db_path, query, parameters=()):
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute(query, parameters).fetchone()
