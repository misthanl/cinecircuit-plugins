import logging
from types import SimpleNamespace

import pytest

from cinecircuit_plugins.douban_rank.timing import stage_timing


@pytest.mark.parametrize("fail", [False, True])
def test_timing_records_debug_duration_and_preserves_error(tmp_path, fail):
    path = tmp_path / "douban.log"
    logger = logging.Logger("douban-timing", logging.DEBUG)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    context = SimpleNamespace(logger=logger)
    try:

        def run():
            with stage_timing(context, "metadata", "douban:movie:123"):
                if fail:
                    raise ValueError("original failure")

        if fail:
            with pytest.raises(ValueError, match="original failure"):
                run()
        else:
            run()
    finally:
        handler.close()
    text = path.read_text(encoding="utf-8")
    assert "DEBUG Rank timing stage=metadata item=douban:movie:123" in text
    assert "seconds=" in text
    assert ("status=interrupted" if fail else "status=completed") in text
