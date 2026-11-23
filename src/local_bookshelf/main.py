from flask import Flask, abort, request

from local_bookshelf.books import books_blueprint
from local_bookshelf.database import Database
from local_bookshelf.log import configure_logging, logger
from local_bookshelf.search import Embedder


def create_app() -> Flask:
    configure_logging()

    logger.info("App starting")
    app = Flask(__name__)
    app.config["TRUSTED_HOSTS"] = ["127.0.0.1", "localhost", "[::1]"]

    database = Database()
    database.initialize()
    app.extensions["bookshelf_db"] = database
    app.extensions["bookshelf_embedder"] = Embedder()
    logger.info("Semantic search ready")

    app.before_request(_check_origin)

    app.register_blueprint(books_blueprint)
    logger.info("Blueprint registered")

    logger.info("App ready")
    return app


def _check_origin() -> None:
    if request.method != "POST":
        return

    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        logger.warning("Cross-site POST blocked")
        abort(403)

    origin = request.headers.get("Origin")
    if origin and origin != request.host_url.rstrip("/"):
        logger.warning("POST origin mismatch")
        abort(403)
