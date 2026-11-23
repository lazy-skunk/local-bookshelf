import hashlib
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from unicodedata import normalize
from urllib.request import urlopen

import numpy as np
from onnxruntime import InferenceSession
from tokenizers import Tokenizer

from local_bookshelf.database import Database
from local_bookshelf.log import logger

_MODEL = "Xenova/multilingual-e5-small"
_REVISION = "761b726dd34fb83930e26aab4e9ac3899aa1fa78"
_CACHE_PREFIX = f"{_MODEL}@{_REVISION}:q8:mean:v1"
_MODEL_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "models"


def _model_file(directory: Path, name: str) -> Path:
    path = directory / name
    if path.is_file():
        return path

    logger.info(f"Downloading: {name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://huggingface.co/{_MODEL}/resolve/{_REVISION}/{name}"

    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        try:
            with urlopen(url, timeout=60) as response:
                shutil.copyfileobj(response, temporary)
            temporary.close()
            os.replace(temporary_path, path)
        finally:
            temporary.close()
            temporary_path.unlink(missing_ok=True)

    logger.info(f"Downloaded: {name}")
    return path


class Embedder:
    def __init__(self) -> None:
        self._directory = _MODEL_DIRECTORY / _REVISION
        self._lock = Lock()
        self._session: InferenceSession | None = None
        self._tokenizer: Tokenizer

    def _load(self) -> InferenceSession:
        with self._lock:
            if self._session is None:
                logger.info("Loading model")

                tokenizer = Tokenizer.from_file(
                    str(_model_file(self._directory, "tokenizer.json"))
                )
                session = InferenceSession(
                    str(
                        _model_file(
                            self._directory, "onnx/model_quantized.onnx"
                        )
                    ),
                    providers=["CPUExecutionProvider"],
                )

                self._tokenizer = tokenizer
                self._session = session
                logger.info("Model ready")

            return self._session

    def chunks(self, text: str) -> Iterator[str]:
        self._load()
        tokens = self._tokenizer.encode(text, add_special_tokens=False).ids

        for start in range(0, len(tokens), 320):
            yield self._tokenizer.decode(
                tokens[start : start + 384], skip_special_tokens=True
            )
            if start + 384 >= len(tokens):
                break

    def embed(self, text: str) -> list[float]:
        session = self._load()
        token_ids = self._tokenizer.encode(text).ids
        if len(token_ids) > 512:
            token_ids = token_ids[:511] + token_ids[-1:]

        inputs = {
            "input_ids": np.array([token_ids], dtype=np.int64),
            "attention_mask": np.ones((1, len(token_ids)), dtype=np.int64),
            "token_type_ids": np.zeros((1, len(token_ids)), dtype=np.int64),
        }

        hidden_states = session.run(None, inputs)[0]
        if not isinstance(hidden_states, np.ndarray):
            raise ValueError("モデルの出力が不正です。")

        vector = hidden_states[0].mean(axis=0)
        vector_norm = np.linalg.norm(vector)
        if (
            vector.shape != (384,)
            or not np.isfinite(vector_norm)
            or not vector_norm
        ):
            raise ValueError("検索ベクトルが不正です。")

        return (vector / vector_norm).tolist()


def keyword_books(
    query: str, books: list[dict[str, str]]
) -> list[dict[str, str]]:
    terms = normalize("NFKC", query).casefold().split()

    matches = []
    for book in books:
        book_text = f"{book['isbn']}\n{book['title']}\n{book['metadataText']}"
        book_text = normalize("NFKC", book_text).casefold()
        if all(term in book_text for term in terms):
            matches.append(book)
    return matches


def rank_books(
    query: str,
    books: list[dict[str, str]],
    database: Database,
    embedder: Embedder,
) -> list[tuple[dict[str, str], float]]:
    if not books:
        logger.info("Embeddings: 0 reused, 0 computed")
        return []

    query_vector = embedder.embed(f"query: {query}")
    results = []
    reused = 0
    computed = 0

    for book in books:
        score = -1.0
        book_text = f"{book['title']}\n{book['metadataText']}"
        for text in embedder.chunks(book_text):
            cache_key = hashlib.sha256(
                f"{_CACHE_PREFIX}\n{text}".encode()
            ).hexdigest()

            vector = database.embedding(cache_key)
            if vector is None:
                vector = embedder.embed(f"passage: {text}")
                database.save_embedding(cache_key, vector)
                computed += 1
            else:
                reused += 1

            vector_norm = np.linalg.norm(vector)
            if vector_norm:
                score = max(
                    score, float(np.dot(query_vector, vector) / vector_norm)
                )

        results.append((book, score))

    logger.info(f"Embeddings: {reused} reused, {computed} computed")
    return sorted(results, key=lambda result: result[1], reverse=True)
