"""Rebuild only the carousel asset using the actual renderer and existing photos."""
import argparse
import io
import json
import hashlib
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root),str(root.parent/'cinecircuit')]
from PIL import Image
from cinecircuit_plugins.media_cover_generator import encoding
from cinecircuit_plugins.media_cover_generator.renderer import CoverRenderer,CoverRenderOptions

parser=argparse.ArgumentParser()
parser.add_argument('--development-ffmpeg',type=Path)
args=parser.parse_args()
if args.development_ffmpeg:
    encoding.FFMPEG_EXECUTABLE=args.development_ffmpeg.resolve()
assets=root/'cinecircuit_plugins/media_cover_generator/assets'
sources=[p.read_bytes() for p in sorted(assets.glob('source-*.jpg'))]
provenance=assets/'sample-provenance.json'
document=json.loads(provenance.read_text(encoding='utf-8'))
for style,name,photos in [('single','sample-animated.webp',sources[:2]),('diagonal','sample-animated-diagonal.webp',sources)]:
    data=CoverRenderer().render_animated(photos,title='电影典藏',subtitle='MOVIE COLLECTION',item_count=0,
        options=CoverRenderOptions(style=style,width=1280,height=720,show_count=False),image_format='webp',duration_seconds=3,frames_per_second=12)
    with Image.open(io.BytesIO(data)) as image:
        assert image.size==(1280,720) and image.n_frames>20
        print({'file':name,'frames':image.n_frames,'bytes':len(data)},flush=True)
        frame_count=image.n_frames
    (assets/name).write_bytes(data)
    entry=next(item for item in document['outputs'] if item['file']==name)
    entry.update(width=1280,height=720,frames=frame_count,requested_fps=12,duration_seconds=3,sha256=hashlib.sha256(data).hexdigest(),source_assets=[p.name for p in sorted(assets.glob('source-*.jpg'))][:len(photos)])
provenance.write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
