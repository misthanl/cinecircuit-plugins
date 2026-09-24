"""Release cyclic HTML trees at the end of each parsing operation."""

from collections.abc import Iterator
from contextlib import contextmanager
from bs4 import BeautifulSoup


@contextmanager
def parsed_page(content: bytes) -> Iterator[BeautifulSoup]:
    page = BeautifulSoup(content, "html.parser")
    try:
        yield page
    finally:
        page.clear(decompose=True)
        page.decompose()
