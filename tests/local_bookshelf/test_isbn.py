import pytest

from local_bookshelf.isbn import (
    NAMESPACES,
    normalize_isbn,
    parse_isbn_response,
)

ISBN = "9784000103435"


@pytest.mark.parametrize(
    ("isbn", "expected"),
    [
        ("９７８４０００１０３４３５", ISBN),
        ("978-4-00-010343-5", ISBN),
        ("4-00-010343-1", ISBN),
        ("0-8044-2957-x", "9780804429573"),
    ],
)
def test_normalize_isbn_canonicalizes_input(isbn: str, expected: str) -> None:
    assert normalize_isbn(isbn) == expected


@pytest.mark.parametrize("isbn", ["9784000103436", "4-00-010343-2", "123"])
def test_normalize_isbn_rejects_invalid_input(isbn: str) -> None:
    with pytest.raises(ValueError):
        normalize_isbn(isbn)


def test_parse_isbn_response_extracts_nested_metadata() -> None:
    namespaces = " ".join(
        f'xmlns:{prefix}="{uri}"' for prefix, uri in NAMESPACES.items()
    )
    xml = f"""<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
      <records><record><recordData><rdf:RDF {namespaces}>
        <dcndl:BibAdminResource rdf:about="https://ndlsearch.ndl.go.jp/books/1"/>
        <dcndl:BibResource>
          <dcterms:title>シリーズ</dcterms:title>
          <dcndl:volume>3</dcndl:volume>
          <dcndl:partInformation><rdf:Description>
            <dcterms:title>巻の書名</dcterms:title><dc:creator>著者</dc:creator>
          </rdf:Description></dcndl:partInformation>
          <dcterms:publisher><foaf:Agent><foaf:name>出版社</foaf:name></foaf:Agent></dcterms:publisher>
          <dcterms:subject><rdf:Description><rdf:value>主題</rdf:value></rdf:Description></dcterms:subject>
          <dcterms:tableOfContents><rdf:Description>
            <dcterms:title>第一章</dcterms:title>
          </rdf:Description></dcterms:tableOfContents>
          <dcndl:edition>第2版</dcndl:edition>
        </dcndl:BibResource>
        <dcndl:Item><dcterms:description>所蔵場所</dcterms:description></dcndl:Item>
      </rdf:RDF></recordData></record></records>
    </searchRetrieveResponse>"""
    book = parse_isbn_response(xml, ISBN)
    assert book is not None
    assert book["title"] == "巻の書名（シリーズ）"
    assert book["author"] == "著者"
    assert book["publisher"] == "出版社"
    assert book["subjects"] == "主題"
    assert book["tableOfContents"] == "第一章"
    assert book["url"] == "https://ndlsearch.ndl.go.jp/books/1"
    assert book["sourceXml"] == xml
    assert "第2版" in book["metadataText"]
    assert "所蔵場所" not in book["metadataText"]
