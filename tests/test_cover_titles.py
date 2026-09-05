import pytest

from cinecircuit_plugins.media_cover_generator.plugin import LibraryArtworkPlugin


@pytest.mark.parametrize('config,expected', [
    ({}, ('外语电影', '')),
    ({'title_config': ''}, ('外语电影', '')),
    ({'title_config': '外语电影=精选电影'}, ('精选电影', '')),
    ({'title_config': '外语电影=精选电影|'}, ('精选电影', '')),
    ({'title_config': '外语电影=精选电影|   '}, ('精选电影', '')),
    ({'title_config': '外语电影=精选电影|WORLD CINEMA'}, ('精选电影', 'WORLD CINEMA')),
    ({'title_map': {'1': {'subtitle': ''}}}, ('外语电影', '')),
    ({'title_map': {'1': {'subtitle': 'CUSTOM'}}}, ('外语电影', 'CUSTOM')),
    ({'title_map': {'1': '自定义标题'}}, ('自定义标题', '')),
    ({'title_map': {}, 'title_config': '外语电影=外语电影|WY MOVIES'}, ('外语电影', 'WY MOVIES')),
    ({'title_map': {'1': {'subtitle': 'OLD'}}, 'title_config': '外语电影=外语电影|WY MOVIES'}, ('外语电影', 'WY MOVIES')),
    ({'title_map': {'1': {'subtitle': 'OLD'}}, 'title_config': '外语电影=外语电影|'}, ('外语电影', '')),
    ({'title_map': {'1': {'subtitle': 'OLD'}}, 'title_config': '其他=其他|OTHER'}, ('外语电影', 'OLD')),
])
def test_only_explicit_english_titles_are_used(config, expected):
    assert LibraryArtworkPlugin()._titles(config, {'id': '1', 'name': '外语电影', 'collection_type': 'movies'}) == expected
