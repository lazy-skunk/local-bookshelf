import re
from unicodedata import normalize
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring

from local_bookshelf.log import logger

NAMESPACES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcndl": "http://ndl.go.jp/dcndl/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
}


def _isbn13_sum(value: str) -> int:
    return sum(
        int(digit) * (3 if index % 2 else 1)
        for index, digit in enumerate(value)
    )


def normalize_isbn(value: str) -> str:
    isbn = re.sub(r"[\s-]", "", normalize("NFKC", value)).upper()

    if re.fullmatch(r"[0-9]{9}[0-9X]", isbn):
        weighted_sum = sum(
            (10 if digit == "X" else int(digit)) * (10 - index)
            for index, digit in enumerate(isbn)
        )
        if weighted_sum % 11 == 0:
            isbn13_body = "978" + isbn[:9]
            return isbn13_body + str(-_isbn13_sum(isbn13_body) % 10)

    if re.fullmatch(r"97[89][0-9]{10}", isbn) and _isbn13_sum(isbn) % 10 == 0:
        return isbn

    raise ValueError("ISBN が不正です。")


def _extract_texts(node: Element) -> list[str]:
    direct_text = (node.text or "").strip()
    if direct_text:
        return [direct_text]

    for tag in ("rdf:value", "foaf:name", "rdf:Description", "foaf:Agent"):
        children = node.findall(tag, NAMESPACES)
        if children:
            return [
                value for child in children for value in _extract_texts(child)
            ]

    return []


def _extract_tag_texts(node: Element, tag: str) -> list[str]:
    return [
        value
        for child in node.findall(tag, NAMESPACES)
        for value in _extract_texts(child)
    ]


def parse_isbn_response(xml: str, isbn: str) -> dict[str, str] | None:
    response_root = fromstring(xml)
    rdf_record = response_root.find(
        "./{*}records/{*}record/{*}recordData/rdf:RDF", NAMESPACES
    )
    if rdf_record is None:
        return None

    for bibliographic_resource in rdf_record.findall(
        "dcndl:BibResource", NAMESPACES
    ):
        titles = _extract_tag_texts(bibliographic_resource, "dcterms:title")
        if titles:
            break
    else:
        return None

    title = titles[0]
    authors = _extract_tag_texts(bibliographic_resource, "dcterms:creator")

    part_elements = bibliographic_resource.findall(
        "dcndl:partInformation", NAMESPACES
    )
    if len(part_elements) == 1 and _extract_tag_texts(
        bibliographic_resource, "dcndl:volume"
    ):
        part_description = part_elements[0].find("rdf:Description", NAMESPACES)
        volume_element = (
            part_elements[0] if part_description is None else part_description
        )
        part_titles = _extract_tag_texts(volume_element, "dcterms:title")
        if part_titles and part_titles[0] != title:
            title = f"{part_titles[0]}（{title}）"
            authors = _extract_tag_texts(volume_element, "dc:creator")

    contents_texts = []
    for contents_entry in bibliographic_resource.findall(
        "dcterms:tableOfContents", NAMESPACES
    ):
        contents_descriptions = contents_entry.findall(
            "rdf:Description", NAMESPACES
        )
        contents_texts.extend(
            [
                value
                for node in contents_descriptions
                for value in _extract_tag_texts(node, "dcterms:title")
            ]
            if contents_descriptions
            else _extract_texts(contents_entry)
        )

    bibliographic_admin = rdf_record.find("dcndl:BibAdminResource", NAMESPACES)
    publication_date_tag = (
        "dcterms:date"
        if bibliographic_resource.find("dcterms:date", NAMESPACES) is not None
        else "dcterms:issued"
    )

    return {
        "isbn": isbn,
        "sourceXml": xml,
        "metadataText": "\n".join(
            dict.fromkeys(
                text.strip()
                for text in bibliographic_resource.itertext()
                if text.strip()
            )
        ),
        "title": title,
        "author": "、".join(
            authors or _extract_tag_texts(bibliographic_resource, "dc:creator")
        ),
        "publisher": "、".join(
            _extract_tag_texts(bibliographic_resource, "dcterms:publisher")
        ),
        "publicationDate": "、".join(
            _extract_tag_texts(bibliographic_resource, publication_date_tag)
        ),
        "subjects": "\n".join(
            _extract_tag_texts(bibliographic_resource, "dcterms:subject")
            + _extract_tag_texts(bibliographic_resource, "dc:subject")
        ),
        "description": "\n".join(
            _extract_tag_texts(bibliographic_resource, "dcterms:abstract")
        ),
        "tableOfContents": "\n".join(contents_texts),
        "url": bibliographic_admin.get(f"{{{NAMESPACES['rdf']}}}about", "")
        if bibliographic_admin is not None
        else "",
    }


def publication_order(book: dict[str, str]) -> tuple[int, int]:
    publication_date = normalize("NFKC", book["publicationDate"]).strip()
    date_match = re.match(
        r"^([0-9]{4})(?![0-9])(?:\s*[.年/-]\s*([0-9]{1,2}))?", publication_date
    )
    if date_match is None:
        return (0, 0)

    month = int(date_match[2] or 0)
    return (int(date_match[1]), month if 1 <= month <= 12 else 0)


def lookup_isbn(isbn: str) -> dict[str, str] | None:
    logger.info("ISBN lookup")

    query = urlencode(
        {
            "operation": "searchRetrieve",
            "query": f'isbn="{isbn}" AND dpid=iss-ndl-opac',
            "recordSchema": "dcndl",
            "recordPacking": "xml",
            "maximumRecords": "1",
        }
    )

    with urlopen(
        f"https://ndlsearch.ndl.go.jp/api/sru?{query}", timeout=15
    ) as response:
        xml = response.read().decode("utf-8-sig")
    logger.info("Bibliographic XML received")

    book = parse_isbn_response(xml, isbn)
    if book is not None:
        logger.info("Bibliographic record parsed")
    return book
