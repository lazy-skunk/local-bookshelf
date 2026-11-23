import logging

from flask.logging import default_handler

logger = logging.getLogger("local_bookshelf")


def configure_logging() -> None:
    logger.setLevel(logging.INFO)
    if not logger.hasHandlers():
        logger.addHandler(default_handler)
