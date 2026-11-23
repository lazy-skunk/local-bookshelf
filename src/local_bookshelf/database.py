import json
import sqlite3
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path

from local_bookshelf.isbn import parse_isbn_response, publication_order
from local_bookshelf.log import logger

_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data/bookshelf.sqlite"


class Database:
    def __init__(self) -> None:
        self._path = _DATABASE_PATH

    def initialize(self) -> None:
        logger.info(f"Opening DB: {self._path}")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS books (
                    isbn TEXT PRIMARY KEY NOT NULL,
                    sourceXml TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS embeddings (
                    key TEXT PRIMARY KEY,
                    vector TEXT NOT NULL
                );
                """
            )

        logger.info("DB ready")

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection]:
        with closing(sqlite3.connect(self._path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            yield connection

    def books(self) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT isbn, sourceXml FROM books"
            ).fetchall()

        books = [Database._parse_book(row) for row in rows]
        logger.info(f"Books loaded: {len(books)}")
        return sorted(books, key=publication_order, reverse=True)

    def book(self, isbn: str) -> dict[str, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT isbn, sourceXml FROM books WHERE isbn = ?", (isbn,)
            ).fetchone()
        if row is None:
            logger.warning("Book missing")
            return None

        book = Database._parse_book(row)
        logger.info("Book loaded")
        return book

    @staticmethod
    def _parse_book(row: sqlite3.Row) -> dict[str, str]:
        book = parse_isbn_response(row["sourceXml"], row["isbn"])
        if book is None:
            raise ValueError(f"Missing bibliographic record: {row['isbn']}")
        return book

    def save(self, isbn: str, source_xml: str) -> bool:
        logger.info("Saving book")
        with self._connect() as connection:
            saved = (
                connection.execute(
                    "INSERT INTO books (isbn, sourceXml) VALUES (?, ?) "
                    "ON CONFLICT (isbn) DO NOTHING",
                    (isbn, source_xml),
                ).rowcount
                == 1
            )

        if saved:
            logger.info("Book saved")
        else:
            logger.warning("Book already exists")
        return saved

    def remove(self, isbn: str) -> None:
        logger.info("Deleting book")
        with self._connect() as connection:
            deleted_count = connection.execute(
                "DELETE FROM books WHERE isbn = ?", (isbn,)
            ).rowcount
        logger.info(f"Books deleted: {deleted_count}")

    def embedding(self, key: str) -> list[float] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT vector FROM embeddings WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row["vector"]) if row else None

    def save_embedding(self, key: str, vector: list[float]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO embeddings (key, vector) VALUES (?, ?) "
                "ON CONFLICT DO NOTHING",
                (key, json.dumps(vector)),
            )
