import io
from types import SimpleNamespace

from PIL import Image, ImageDraw

from cinecircuit_plugins.media_cover_generator import encoding, preview
from cinecircuit_plugins.media_cover_generator.plugin import ArtworkGenerationRun, LibraryArtworkPlugin
from cinecircuit_plugins.media_cover_generator.renderer import CoverRenderer, CoverRenderOptions


def photos():
    result = []
    for color in ('red', 'blue'):
        output = io.BytesIO()
        Image.new('RGB', (320, 180), color).save(output, 'PNG')
        result.append(output.getvalue())
    return result


def test_wedge_is_dynamic_and_uses_animation_settings():
    run = ArtworkGenerationRun(LibraryArtworkPlugin(), SimpleNamespace(config={
        'cover_style_base':'animated_wedge', 'animation_resolution':'640x360', 'animation_format':'gif'}))
    assert run.animated and run.options.style == 'wedge'
    assert (run.options.width, run.options.height) == (640, 360)


def test_wedge_dissolves_background_and_photos_but_not_lettering(monkeypatch):
    frames = []
    monkeypatch.setattr(encoding, 'encode_frames', lambda values, **kwargs: frames.extend(values) or b'encoded')
    def lettering(self, frame, **kwargs):
        ImageDraw.Draw(frame).rectangle((20, 80, 45, 90), fill='white')
    monkeypatch.setattr(CoverRenderer, '_draw_copy', lettering)
    result = CoverRenderer().render_animated(photos(), title='test', subtitle='', item_count=0,
        options=CoverRenderOptions(style='wedge', width=320, height=180, background_grain=0),
        duration_seconds=2, frames_per_second=30)
    assert result == b'encoded' and len(frames) == 60
    assert all(frame.getpixel((25, 85)) == (255,255,255,255) for frame in frames)
    assert frames[0].getpixel((300,90)) != frames[30].getpixel((300,90))
    assert frames[0].getpixel((5,5)) != frames[30].getpixel((5,5))
    # An intermediate dissolve, and the end returns close to the first frame.
    assert frames[24].getpixel((300,90)) not in [frames[0].getpixel((300,90)),frames[30].getpixel((300,90))]
    assert max(abs(a-b) for a,b in zip(frames[-1].getpixel((300,90)), frames[0].getpixel((300,90)))) < 5


def test_wedge_sample_is_cached_at_720p(monkeypatch):
    calls=[]
    def render(self, sources, **kwargs):
        calls.append(kwargs)
        return b'webp-sample'
    preview._wedge_sample.cache_clear()
    monkeypatch.setattr(CoverRenderer, 'render_animated', render)
    try:
        first=preview.read_sample('animated_wedge','1')
        assert first == preview.read_sample('animated_wedge','1')
        assert first['width']==1280 and first['height']==720
        assert len(calls)==1 and calls[0]['options'].style=='wedge'
    finally:
        preview._wedge_sample.cache_clear()
