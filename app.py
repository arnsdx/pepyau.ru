import argparse
import logging
import os
import re
import sqlite3
import time
from http import HTTPStatus
from pathlib import Path
from threading import Thread
from wsgiref.util import FileWrapper

import catalog

PROJECT = Path(__file__).resolve().parent
PAGE = (PROJECT / "index.html").read_bytes()
FIT_SCRIPT = (PROJECT / "fit.js").read_bytes()
IMAGE_URL = re.compile(r"/image/([a-f0-9]{64})")
PAGE_POLICY = "default-src 'none'; img-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'"
LOGGER = logging.getLogger(__name__)


def create_app(images_dir, db_path):
    images_dir = Path(images_dir).resolve()
    db_path = Path(db_path).resolve()

    def app(environ, start_response):
        method = environ["REQUEST_METHOD"]
        path = environ["PATH_INFO"]

        def send_headers(status, mime, length, extra=()):
            start_response(f"{status.value} {status.phrase}", [
                ("Content-Type", mime),
                ("Content-Length", str(length)),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
                *extra,
            ])

        def respond(status, body, mime="text/plain; charset=utf-8", extra=()):
            send_headers(status, mime, len(body), extra)
            return [] if method == "HEAD" else [body]

        if path == "/api/v2":
            return respond(
                HTTPStatus.UNAUTHORIZED,
                b'{"code":401,"error":"Unauthorized"}',
                "application/json",
                [("WWW-Authenticate", 'Bearer realm="api"')],
            )

        image_url = IMAGE_URL.fullmatch(path)
        if path not in {"/", "/fit.js"} and not image_url:
            return respond(HTTPStatus.NOT_FOUND, b"Not found\n")
        if method not in {"GET", "HEAD"}:
            return respond(
                HTTPStatus.METHOD_NOT_ALLOWED,
                b"Method not allowed\n",
                extra=[("Allow", "GET, HEAD")],
            )

        try:
            if path == "/fit.js":
                return respond(HTTPStatus.OK, FIT_SCRIPT, "text/javascript; charset=utf-8")
            if path == "/":
                selected = catalog.lookup(db_path, catalog.RANDOM_IMAGE_SQL)
                if selected is None:
                    return respond(HTTPStatus.SERVICE_UNAVAILABLE, b"No indexed images\n")
                return respond(
                    HTTPStatus.OK,
                    PAGE.replace(b"__IMAGE_ID__", selected[0].encode("ascii")),
                    "text/html; charset=utf-8",
                    [("Content-Security-Policy", PAGE_POLICY)],
                )

            selected = catalog.lookup(
                db_path, "SELECT path, content_type FROM images WHERE id = ?", (image_url[1],)
            )
            if selected is None:
                return respond(HTTPStatus.NOT_FOUND, b"Not found\n")
            relative_path, mime = selected
            try:
                image, length = catalog.open_image(images_dir, relative_path)
            except (FileNotFoundError, NotADirectoryError):
                return respond(HTTPStatus.NOT_FOUND, b"Not found\n")

            try:
                if catalog.content_type(image.read(12)) != mime:
                    image.close()
                    return respond(HTTPStatus.NOT_FOUND, b"Not found\n")
                image.seek(0)
                send_headers(HTTPStatus.OK, mime, length)
                if method == "HEAD":
                    image.close()
                    return []
                return environ.get("wsgi.file_wrapper", FileWrapper)(image, 65536)
            except BaseException:
                image.close()
                raise
        except (OSError, sqlite3.Error):
            LOGGER.exception("Could not read the image catalog or file")
            return respond(HTTPStatus.SERVICE_UNAVAILABLE, b"Image catalog unavailable\n")

    return app


def update_index(images_dir, db_path):
    try:
        count = catalog.reindex(images_dir, db_path)
    except (OSError, sqlite3.Error):
        LOGGER.exception("Indexing failed")
        return False
    LOGGER.info("Indexed %d images from %s", count, images_dir)
    return True


def index_on_timer(images_dir, db_path, interval):
    while True:
        time.sleep(interval)
        update_index(images_dir, db_path)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Serve a random image from a local catalog.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("index", help="Update the SQLite catalog and exit.")
    server = commands.add_parser("serve", help="Index images and start the HTTP server.")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", default=8080, type=int)
    args = parser.parse_args()

    images_dir = Path(os.environ.get("IMAGES_DIR", "images")).resolve()
    db_path = Path(os.environ.get("DB_PATH", "data/catalog.sqlite3")).resolve()
    if args.command == "index":
        return 0 if update_index(images_dir, db_path) else 1

    try:
        interval = int(os.environ.get("INDEX_INTERVAL_SECONDS", "300"))
        if interval < 0:
            raise ValueError
    except ValueError:
        parser.error("INDEX_INTERVAL_SECONDS must be a nonnegative integer")

    from waitress import serve

    update_index(images_dir, db_path)
    if interval:
        Thread(target=index_on_timer, args=(images_dir, db_path, interval), daemon=True).start()

    serve(
        create_app(images_dir, db_path),
        host=args.host,
        port=args.port,
        max_request_body_size=16 * 1024,
        max_request_header_size=32 * 1024,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
