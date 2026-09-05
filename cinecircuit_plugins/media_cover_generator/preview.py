"""Bounded, side-effect-free sample rendering. Never reads or writes a media server."""
import asyncio
import array
import sys
import uuid
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from .renderer import CoverRenderer, CoverRenderOptions
from .runtime_state import state

_semaphore = asyncio.Semaphore(1)
_jobs = state.jobs


def start_preview(plugin, config: dict, font_path: Path) -> dict:
    if any(not task.done() for task in _jobs.values()):
        raise ValueError('已有预览正在生成，请稍后重试')
    _jobs.clear()
    identity = uuid.uuid4().hex
    task = asyncio.create_task(render_preview(plugin,config,font_path))
    _jobs[identity] = task
    def finished(result):
        # Retrieve exceptions even if the requesting browser was closed.
        if not result.cancelled():
            result.exception()
        asyncio.get_running_loop().call_later(120,lambda: _jobs.pop(identity,None))
    task.add_done_callback(finished)
    return {'status':'rendering','preview_id':identity}


def preview_status(identity: str) -> dict:
    task = _jobs.get(identity)
    if task is None:
        raise ValueError('预览已过期，请重新生成')
    if not task.done():
        return {'status':'rendering','preview_id':identity}
    return {'status':'complete',**task.result()}


@lru_cache(maxsize=1)
def _wedge_sample() -> bytes:
    # Reuse bundled source photos instead of adding another large animation ZIP asset.
    sources = [p.read_bytes() for p in sorted((Path(__file__).parent/'assets').glob('source-*.jpg'))][:3]
    return CoverRenderer().render_animated(sources, title='电影典藏', subtitle='MOVIE COLLECTION',
        item_count=0, options=CoverRenderOptions(style='wedge', width=1280, height=720, show_count=False),
        image_format='webp', duration_seconds=6, frames_per_second=12)


def read_sample(style: str, variant: str) -> dict:
    if style in {'animated','animated_diagonal','animated_wedge'}:
        name = 'sample-animated.webp' if style == 'animated' else 'sample-animated-diagonal.webp'
        data = _wedge_sample() if style == 'animated_wedge' else (Path(__file__).parent / 'assets' / name).read_bytes()
        words = array.array('I')
        words.frombytes(data + b'\0' * (-len(data) % 4))
        if sys.byteorder != 'little':
            words.byteswap()
        return {'image_words':words.tolist(),'byte_length':len(data),'mime':'image/webp','width':1280,'height':720}
    names = {key: f'sample-{key}' for key in ('single','poster','diagonal','duo','stack','editorial','panorama','cinema','echo','wedge')}
    if style == 'multi':
        name = {'1':'variant-grid','2':'variant-focus','3':'variant-split','4':'variant-triptych'}.get(variant)
    else:
        name = names.get(style)
    if name is None:
        raise ValueError('未知封面样式')
    data = (Path(__file__).parent / 'assets' / f'{name}.jpg').read_bytes()
    return {'image_bytes':list(data), 'mime':'image/jpeg', 'width':1920,'height':1080}


async def render_preview(plugin, config: dict, font_path: Path) -> dict:
    from .plugin import ArtworkGenerationRun

    run = ArtworkGenerationRun(plugin, SimpleNamespace(config=config))
    # Preserve selected animation resolution. Pack transport to avoid one Python
    # integer per byte and the host's string-redaction limits.
    max_width, max_height = (1920,1080)
    factor = min(max_width / run.options.width, max_height / run.options.height, 1)
    options = replace(run.options, width=max(1,round(run.options.width*factor)),
                      height=max(1,round(run.options.height*factor)), jpeg_quality=94)
    title, subtitle = '电影典藏', ''
    first_line = str(config.get('title_config') or '').splitlines()
    if first_line and '=' in first_line[0]:
        labels = first_line[0].split('=',1)[1].split('|',1)
        title = labels[0].strip() or title
        subtitle = labels[1].strip() if len(labels)>1 else subtitle
    # Input and pixel budgets are independent of arbitrary custom output dimensions.
    async with _semaphore:
        def render():
            sources = [p.read_bytes() for p in sorted((Path(__file__).parent/'assets').glob('source-*.jpg'))][:run.source_limit]
            renderer=CoverRenderer(font_path)
            common=dict(title=title[:120], subtitle=subtitle[:180], item_count=128, options=options)
            if run.animated:
                data=renderer.render_animated(sources,**common,image_format='webp',
                    duration_seconds=min(60,max(2,int(config.get('animation_duration') or 6))),
                    frames_per_second=min(30,max(1,int(config.get('animation_fps') or 12))))
                mime='image/webp'
            else:
                data=renderer.render(sources,**common)
                mime='image/jpeg'
            words = array.array('I')
            words.frombytes(data + b'\0' * (-len(data) % 4))
            if sys.byteorder != 'little':
                words.byteswap()
            return {'image_words':words.tolist(), 'byte_length':len(data), 'mime':mime,
                    'width':common['options'].width,'height':common['options'].height}
        return await asyncio.to_thread(render)
