"""Reproduce shipped previews using TMDB originals and the production CoverRenderer.

Run from the plugin repository with the host Python. Static outputs are the exact
1920x1080 JPEG bytes returned by render(), without resizing or re-encoding.
"""
import concurrent.futures
import hashlib
import io
import json
from pathlib import Path
import sys
import urllib.request

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / 'cinecircuit'))
from cinecircuit_plugins.media_cover_generator.renderer import CoverRenderer, CoverRenderOptions

ASSETS = ROOT / 'cinecircuit_plugins/media_cover_generator/assets'
CACHE = ROOT / '.planning/cover-hd/source-images'


def source(movie):
    url = 'https://image.tmdb.org/t/p/original' + movie['poster_path']
    path = CACHE / f"{movie['id']}.jpg"
    if not path.exists():
        with urllib.request.urlopen(url, timeout=60) as response:
            path.write_bytes(response.read())
    content = path.read_bytes()
    with Image.open(io.BytesIO(content)) as image:
        assert image.width >= 1000, f"TMDB original too small: {movie['id']}"
        movie['source_dimensions'] = list(image.size)
    movie['source_url'] = url
    movie['source_sha256'] = hashlib.sha256(content).hexdigest()
    return content


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    movies = json.loads((ASSETS / 'sample-sources.json').read_text(encoding='utf-8'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        posters = list(executor.map(source, movies))
    renderer = CoverRenderer()
    for index,content in enumerate(posters):
        with Image.open(io.BytesIO(content)) as image:
            image.thumbnail((720,1080),Image.Resampling.LANCZOS)
            image.convert('RGB').save(ASSETS/f'source-{index:02}.jpg',quality=92)
    common = dict(title='电影典藏', subtitle='MOVIE COLLECTION', item_count=128)
    layouts = {'sample-single':'spotlight', 'sample-multi':'mosaic', 'sample-poster':'filmstrip',
               'variant-grid':'mosaic', 'variant-focus':'mosaic_focus', 'variant-split':'split', 'variant-triptych':'triptych',
               **{f'sample-{style}':style for style in ['diagonal','duo','stack','editorial','panorama','cinema','echo','wedge']}}
    outputs = []
    for name, style in layouts.items():
        labels = common
        content = renderer.render(posters, **labels, options=CoverRenderOptions(style=style, width=1920, height=1080, jpeg_quality=96,show_count=False))
        path = ASSETS / f'{name}.jpg'
        path.write_bytes(content)
        with Image.open(io.BytesIO(content)) as thumbnail:
            thumbnail.thumbnail((960, 540), Image.Resampling.LANCZOS)
            thumbnail.save(ASSETS / f'thumb-{name}.jpg', quality=94)
        outputs.append({'file':path.name,'width':1920,'height':1080,'renderer_style':style,'sha256':hashlib.sha256(content).hexdigest()})
        print(path.name, len(content))
    content = renderer.render_animated(posters[:2], **common, options=CoverRenderOptions(width=1280, height=720,show_count=False), image_format='webp', duration_seconds=3, frames_per_second=12)
    (ASSETS / 'sample-animated.webp').write_bytes(content)
    moving = renderer.render_animated(posters, **common, options=CoverRenderOptions(style='diagonal',width=1280,height=720,show_count=False),image_format='webp',duration_seconds=3,frames_per_second=12)
    (ASSETS/'sample-animated-diagonal.webp').write_bytes(moving)
    outputs.append({'file':'sample-animated.webp','width':1280,'height':720,'frames':36,'sha256':hashlib.sha256(content).hexdigest()})
    outputs.append({'file':'sample-animated-diagonal.webp','width':1280,'height':720,'frames':36,'sha256':hashlib.sha256(moving).hexdigest()})
    (ASSETS / 'sample-provenance.json').write_text(json.dumps({'renderer':'CoverRenderer.render / render_animated','static_jpeg_quality':96,'postprocess':None,'movies':movies,'outputs':outputs},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('sample-animated.webp',len(content))


if __name__ == '__main__':
    main()
