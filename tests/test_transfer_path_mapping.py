import pytest

from cinecircuit_plugins.torrent_transfer.path_mapping import mapped_save_path


def test_paired_mappings_use_longest_matching_directory():
    config = {"path_mappings": " /data # /target \n\n/data/films#/movies"}
    assert mapped_save_path("/data/films/A", config) == "/movies/A"
    assert mapped_save_path("/data/B", config) == "/target/B"
    with pytest.raises(ValueError, match="未命中"):
        mapped_save_path("/data2/A", config)


def test_legacy_mapping_and_empty_mapping_remain_supported():
    assert mapped_save_path("/data/A", {"frompath": "/data", "topath": "/target"}) == "/target/A"
    assert mapped_save_path("/data/A", {"path_mappings": "", "frompath": "", "topath": ""}) == "/data/A"


@pytest.mark.parametrize("value", ["/data", "/data#", "#/target", "/data#/target#extra"])
def test_invalid_pair_cannot_silently_reuse_original_path(value):
    with pytest.raises(ValueError, match="第 1 行"):
        mapped_save_path("/data/A", {"path_mappings": value})
