import asyncio
from types import SimpleNamespace

import pytest

from cinecircuit_plugins.cloud_copy import CloudCopyPlugin, statistics
from cinecircuit_plugins.cloud_copy.journal import iter_batches
from test_cloud_copy import context


@pytest.mark.parametrize("page", [1, 32, 33, 65, 999])
def test_statistics_pages_are_stable_and_display_window_is_bounded(monkeypatch, page):
    ctx = context("source", "target")
    for i in range(515):
        ctx.state.set(
            f"records-{i:04}",
            {
                str(i): {
                    "path": f"movie-{i}.mkv",
                    "updated_at": i // 3,
                    "status": "completed",
                    "method": "rapid",
                }
            },
        )
    original = statistics.nsmallest
    windows = []

    def bounded(size, rows, **kwargs):
        windows.append(size)
        return original(size, rows, **kwargs)

    monkeypatch.setattr(statistics, "nsmallest", bounded)
    result = asyncio.run(
        CloudCopyPlugin().handle_api(SimpleNamespace(action="status", query={"page": page}), ctx)
    )
    ordered = sorted(range(515), key=lambda i: (-(i // 3), f"rule::{i}"))
    requested = min(page, 65)
    assert [row["identity"] for row in result["records"]] == list(
        map(str, ordered[(requested - 1) * 8 : requested * 8])
    )
    assert result["counts"]["completed"] == result["total"] == 515
    assert result["page"] == requested
    assert max(windows) <= statistics.WINDOW_SIZE
    ctx.sdk.require.return_value.file_page.assert_not_called()


def test_batch_iterator_rejects_stalled_page():
    class StalledIndex:
        def list(self, **_):
            return [{"key": "task-a", "value": {}}] * 500

    with pytest.raises(ValueError, match="分页没有前进"):
        list(iter_batches(StalledIndex()))
