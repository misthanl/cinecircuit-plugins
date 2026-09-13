from cinecircuit_plugins.subtitle_manager.statistics import summarize

EXPECTED_SUMMARY_ROWS = 4
SUMMARY_ROW_LIMIT = 500
OVER_LIMIT_ROWS = SUMMARY_ROW_LIMIT + 1


def test_media_counts_are_not_candidate_failure_counts():
    result = summarize(
        [
            {
                "title": "成功",
                "saved": ["a", "b"],
                "failed": 7,
                "details": [
                    {"status": "saved", "bilingual": True, "converted": True},
                    {"status": "saved", "bilingual": False, "converted": False},
                ],
            },
            {"title": "跳过", "reason": "chinese_media"},
            {"title": "失败", "failed": 4},
        ]
    )
    assert [
        result[k]
        for k in (
            "media",
            "saved",
            "completed_media",
            "skipped",
            "failed",
            "bilingual",
            "converted",
        )
    ] == [3, 2, 1, 1, 1, 1, 1]
    assert result["total_rows"] == EXPECTED_SUMMARY_ROWS
    assert result["rows"][2]["reason"] == "按设置跳过中文原声媒体"


def test_empty_and_bounded_details():
    assert summarize([])["media"] == 0
    result = summarize(
        [{"media_path": "private/directory/movie.mkv"}] * OVER_LIMIT_ROWS
    )
    assert result["total_rows"] == OVER_LIMIT_ROWS
    assert len(result["rows"]) == SUMMARY_ROW_LIMIT
    assert result["rows"][0]["media"] == "movie.mkv"
