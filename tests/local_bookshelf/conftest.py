from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from local_bookshelf.database import Database
from local_bookshelf.isbn import NAMESPACES, parse_isbn_response


@pytest.fixture
def database(tmp_path: Path, mocker: MockerFixture) -> Database:
    mocker.patch(
        "local_bookshelf.database._DATABASE_PATH",
        new=tmp_path / "bookshelf.sqlite",
    )
    database = Database()
    database.initialize()
    return database


@pytest.fixture
def bibliographic_record() -> Callable[..., dict[str, str]]:
    def make_record(
        isbn: str = "9784000103435", title: str = "設計", date: str = "2026.9"
    ) -> dict[str, str]:
        xml = f"""
        <response><records><record><recordData>
          <rdf:RDF xmlns:rdf="{NAMESPACES["rdf"]}"
                   xmlns:dcndl="{NAMESPACES["dcndl"]}"
                   xmlns:dcterms="{NAMESPACES["dcterms"]}">
            <dcndl:BibResource>
              <dcterms:title>{title}</dcterms:title>
              <dcterms:date>{date}</dcterms:date>
            </dcndl:BibResource>
          </rdf:RDF>
        </recordData></record></records></response>
        """
        book = parse_isbn_response(xml, isbn)
        assert book is not None
        return book

    return make_record
