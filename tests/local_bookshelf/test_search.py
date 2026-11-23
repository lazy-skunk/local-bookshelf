from collections.abc import Callable

from pytest_mock import MockerFixture

from local_bookshelf.database import Database
from local_bookshelf.search import Embedder, keyword_books, rank_books


def test_keyword_books_requires_all_normalized_terms(
    bibliographic_record: Callable[..., dict[str, str]],
) -> None:
    book = bibliographic_record(title="ＡＢＣ設計")
    other_book = bibliographic_record("9780804429573", "設計")
    books = [other_book, book]

    assert keyword_books("ａｂｃ　設計", books) == [book]
    assert keyword_books(book["isbn"], books) == [book]
    assert keyword_books("設計", books) == books
    assert keyword_books("設計 数学", books) == []


def test_rank_books_orders_by_similarity_and_reuses_embeddings(
    database: Database,
    bibliographic_record: Callable[..., dict[str, str]],
    mocker: MockerFixture,
) -> None:
    relevant = bibliographic_record()
    unrelated = bibliographic_record("9780804429573", "数学")
    books = [unrelated, relevant]
    embedder = mocker.create_autospec(Embedder, instance=True)
    embedder.chunks.side_effect = lambda text: iter((text,))
    embedder.embed.side_effect = lambda text: (
        [1.0, 0.0] if "設計" in text else [0.0, 1.0]
    )

    assert rank_books("設計", books, database, embedder) == [
        (relevant, 1.0),
        (unrelated, 0.0),
    ]
    assert embedder.embed.call_count == 3

    embedder.embed.reset_mock()
    assert rank_books("設計", books, database, embedder) == [
        (relevant, 1.0),
        (unrelated, 0.0),
    ]
    embedder.embed.assert_called_once_with("query: 設計")
