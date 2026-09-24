import asyncio
import gc
import weakref

import pytest

from cinecircuit_plugins.subtitle_manager.online_sources.html_page import parsed_page
from cinecircuit_plugins.subtitle_manager.online_sources.subhd import SubHDSource


@pytest.mark.parametrize("error", [None, ValueError, asyncio.CancelledError])
def test_html_tree_is_destroyed_without_waiting_for_gc(error):
    enabled = gc.isenabled()
    gc.disable()
    try:
        try:
            with parsed_page(b"<div><a href='/a/1'>Example</a></div>") as page:
                child = weakref.ref(page.a)
                if error:
                    raise error()
        except (ValueError, asyncio.CancelledError):
            pass
        assert page.decomposed
        assert child() is None
    finally:
        if enabled:
            gc.enable()


def test_subhd_candidates_survive_tree_cleanup():
    cards = SubHDSource._candidate_cards(
        b"<div class='view-text'><a href='/a/123'>Example S01E01</a></div>",
        "https://subhd.tv/search/example",
    )
    candidate = cards["https://subhd.tv/a/123"]
    assert candidate.title == "Example S01E01"
    assert candidate.download_ref == "https://subhd.tv/a/123"
