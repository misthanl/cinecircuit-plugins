import gc
import weakref

import pytest

from cinecircuit_plugins.douban_rank import boards


@pytest.mark.parametrize("kind", ["chart", "top", "invalid"])
def test_board_parsers_release_html_without_gc(monkeypatch, kind):
    original = boards.BeautifulSoup
    references = []

    def track(*args, **kwargs):
        page = original(*args, **kwargs)
        references.append(weakref.ref(page))
        references.append(weakref.ref(page.div))
        return page

    monkeypatch.setattr(boards, "BeautifulSoup", track)
    page = b'<div class="movie_top"><a onclick="mv_week" href="https://movie.douban.com/subject/1/">Film</a></div>'
    enabled = gc.isenabled()
    gc.disable()
    try:
        if kind == "chart":
            assert boards.chart_rows(page, "movie-weekly")[0]["title"] == "Film"
        elif kind == "top":
            assert boards.top_rows(page) == []
        else:
            with pytest.raises(ValueError):
                boards.chart_rows(page, "movie-ustop")
        assert all(reference() is None for reference in references)
    finally:
        if enabled:
            gc.enable()
