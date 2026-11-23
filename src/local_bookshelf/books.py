from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue

from local_bookshelf.isbn import lookup_isbn, normalize_isbn, publication_order
from local_bookshelf.log import logger
from local_bookshelf.search import keyword_books, rank_books

books_blueprint = Blueprint("books", __name__)


def _home(
    isbn_input: str = "", error: str | None = None, status: int = 200
) -> tuple[str, int]:
    query = request.args.get("query", "").strip()
    search_mode = request.args.get("search_mode", "keyword")

    search_error = None
    similarity_by_isbn: dict[str, float] = {}
    database = current_app.extensions["bookshelf_db"]
    books = database.books()

    if query:
        logger.info(f"Search: {search_mode!r}, {len(books)} books")

    if query and search_mode == "semantic":
        try:
            ranked_books = rank_books(
                query,
                books,
                database,
                current_app.extensions["bookshelf_embedder"],
            )
            books = [book for book, _ in ranked_books]
            similarity_by_isbn = {
                book["isbn"]: score for book, score in ranked_books
            }
        except Exception:
            logger.exception("Semantic search failed")
            search_error = (
                "意味検索に失敗しました。"
                "モデルの取得先への接続を確認してください。"
            )
            books = []
            status = 503
    elif query and search_mode == "keyword":
        books = keyword_books(query, books)

    if query and not search_error:
        logger.info(f"Matches: {len(books)}")

    return render_template(
        "index.html",
        books=books,
        publication_year_by_isbn={
            book["isbn"]: publication_order(book)[0] for book in books
        },
        similarity_by_isbn=similarity_by_isbn,
        isbn_input=isbn_input,
        error=error,
        search_error=search_error,
        query=query,
        search_mode=search_mode,
    ), status


@books_blueprint.get("/")
def index() -> tuple[str, int]:
    return _home()


@books_blueprint.post("/books")
def register_isbn() -> ResponseReturnValue:
    logger.info("Book registration")
    value = request.form.get("isbn", "").strip()
    try:
        isbn = normalize_isbn(value)
    except ValueError as error:
        logger.warning("Invalid ISBN")
        return _home(value, str(error), 400)

    logger.info("ISBN validated")
    try:
        result = lookup_isbn(isbn)
    except Exception:
        logger.exception("ISBN lookup failed")
        return _home(
            isbn,
            "書誌情報を取得できませんでした。時間を置いて再試行してください。",
            502,
        )

    if result is None:
        logger.warning("Bibliographic record not found")
        return _home(isbn, "該当する書籍が見つかりませんでした。", 404)

    if not current_app.extensions["bookshelf_db"].save(
        isbn, result["sourceXml"]
    ):
        return _home(isbn, "同じ ISBN の書籍が登録されています。", 409)

    return redirect(url_for("books.detail", isbn=isbn), code=303)


@books_blueprint.get("/books/<isbn>")
def detail(isbn: str) -> str:
    book = current_app.extensions["bookshelf_db"].book(isbn)
    if book is None:
        abort(404)

    return render_template("book.html", book=book)


@books_blueprint.post("/books/<isbn>/delete")
def remove(isbn: str) -> ResponseReturnValue:
    current_app.extensions["bookshelf_db"].remove(isbn)
    return redirect(url_for("books.index"), code=303)
