import io

import pytest
from PIL import Image

from cinecircuit_plugins.media_cover_generator.renderer import CoverRenderer, CoverRenderOptions


def jpeg(color):
    output = io.BytesIO()
    Image.new("RGB", (320, 480), color).save(output, "JPEG")
    return output.getvalue()


@pytest.mark.parametrize("style", ["spotlight", "diagonal", "wedge"])
def test_hidden_library_titles_do_not_change_static_or_animated_images(style):
    renderer = CoverRenderer()
    options = CoverRenderOptions.from_config(
        {
            "style": style,
            "width": 320,
            "height": 180,
            "show_library_title": False,
            "show_count": False,
            "background_grain": 0,
        }
    )
    source = [jpeg((30, 70, 120)), jpeg((90, 40, 60))]
    first = renderer.render(source, title="First", subtitle="FIRST", item_count=12, options=options)
    second = renderer.render(
        source, title="Second", subtitle="SECOND", item_count=12, options=options
    )
    assert first == second
    images = renderer._open_images(source)
    frames_a = list(
        renderer._animation_frames(images, options, (30, 70, 120), 3, "First", "FIRST", 12)
    )
    frames_b = list(
        renderer._animation_frames(images, options, (30, 70, 120), 3, "Second", "SECOND", 12)
    )
    assert len(frames_a) == len(frames_b) == 3
    assert [f.tobytes() for f in frames_a] == [f.tobytes() for f in frames_b]


def test_library_title_defaults_on_and_count_badge_remains_independent():
    from dataclasses import replace

    assert CoverRenderOptions.from_config({}).show_library_title is True
    renderer = CoverRenderer()
    source = [jpeg((30, 70, 120))]
    options = CoverRenderOptions(
        style="diagonal",
        width=320,
        height=180,
        show_library_title=False,
        show_count=False,
        background_grain=0,
    )
    hidden = renderer.render(
        source, title="Movies", subtitle="CINEMA", item_count=12, options=options
    )
    counted = renderer.render(
        source,
        title="Movies",
        subtitle="CINEMA",
        item_count=12,
        options=replace(options, show_count=True),
    )
    titled = renderer.render(
        source,
        title="Movies",
        subtitle="CINEMA",
        item_count=12,
        options=replace(options, show_library_title=True),
    )
    assert hidden != counted
    assert hidden != titled
