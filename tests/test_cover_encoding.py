import io
import asyncio
import importlib
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image

from cinecircuit_plugins.media_cover_generator import encoding
from cinecircuit_plugins.media_cover_generator.plugin import LibraryArtworkPlugin, ArtworkGenerationRun


@pytest.fixture
def storage(tmp_path, monkeypatch):
    root = tmp_path / 'covers'
    for name in ('temp', 'output'):
        (root / name).mkdir(parents=True)
    monkeypatch.setattr(encoding, 'cover_directory', lambda: root)
    return root


def test_default_resolution_and_explicit_values():
    plugin = LibraryArtworkPlugin()
    fields = {f['key']: f for f in plugin.manifest.to_dict()['config_schema']['fields']}
    assert fields['resolution']['default'] == '1080p'
    assert fields['animation_resolution']['default'] == '1920x1080'
    assert fields['animation_format']['default'] == 'webp'
    assert [item['value'] for item in fields['animation_format']['options']] == ['webp','apng','gif']
    assert fields['animation_duration']['default'] == 6
    assert fields['use_primary']['default'] is True
    assert fields['dry_run']['default'] is False
    assert ArtworkGenerationRun(plugin,SimpleNamespace(config={})).dry_run is False
    assert ArtworkGenerationRun(plugin,SimpleNamespace(config={'dry_run':True})).dry_run is True
    assert ArtworkGenerationRun(plugin,SimpleNamespace(config={})).image_sources[0]=='Primary'
    assert ArtworkGenerationRun(plugin,SimpleNamespace(config={'use_primary':False,'image_sources':['Backdrop','Primary']})).image_sources[0]=='Backdrop'
    for style in ('single', 'animated_diagonal'):
        run = ArtworkGenerationRun(plugin, SimpleNamespace(config={'cover_style_base': style}))
        assert (run.options.width, run.options.height) == (1920, 1080)
    run = ArtworkGenerationRun(plugin, SimpleNamespace(config={'cover_style_base':'animated_diagonal','animation_resolution':'320x180'}))
    assert (run.options.width, run.options.height) == (320,180)


def test_animation_settings_belong_only_to_animation_section():
    fields = LibraryArtworkPlugin().manifest.to_dict()['config_schema']['fields']
    direction = [field for field in fields if field['key']=='animation_direction']
    assert len(direction)==1 and direction[0]['section']=='style'
    for key in ('animation_resolution','animation_format','animation_duration','animation_fps'):
        matching = [field for field in fields if field['key']==key]
        assert len(matching)==1
        assert matching[0]['section']=='animation'


def test_storage_switch_order_and_resolution_help():
    fields = LibraryArtworkPlugin().manifest.to_dict()['config_schema']['fields']
    storage = [f for f in fields if f.get('section') == 'storage']
    assert [f['key'] for f in storage] == ['clean_images', 'clean_fonts', 'save_recent_covers', 'skip_unchanged', 'covers_history_limit_per_library', 'covers_page_history_limit']
    assert not storage[3].get('description')
    assert storage[0]['default'] is True
    assert storage[1]['default'] is False
    resolution = next(f for f in fields if f['key'] == 'animation_resolution')
    assert '生成耗时和文件体积' in resolution['description']


@pytest.mark.parametrize('style',['animated','animated_diagonal'])
def test_lazy_carousel_sample_is_real_animation(style):
    import struct
    from cinecircuit_plugins.media_cover_generator.preview import read_sample
    result = read_sample(style, '1')
    data=struct.pack('<'+'I'*len(result['image_words']),*result['image_words'])[:result['byte_length']]
    assert (result['width'],result['height'])==(1280,720)
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (1280, 720)
        assert image.n_frames > 20


@pytest.mark.parametrize('format_name',['apng','gif','webp'])
def test_real_hd_encoding_and_cleanup(storage, format_name, monkeypatch):
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg integration dependency is not installed')
    from pathlib import Path
    monkeypatch.setattr(encoding,'FFMPEG_EXECUTABLE',Path(shutil.which('ffmpeg')))
    frames = (Image.new('RGB',(1920,1080),color) for color in ('red','blue','green','yellow'))
    data = encoding.encode_frames(frames,width=1920,height=1080,frame_count=4,seconds=2,image_format=format_name)
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (1920,1080)
        assert image.n_frames == 4
        image.seek(3)
        image.load()
    assert not list((storage/'temp').iterdir())


@pytest.mark.parametrize('failure',['frames','encoder','timeout','space','busy'])
def test_failures_release_gate_and_clean_only_owned_temp(storage,monkeypatch,failure):
    sentinel = storage/'temp'/'user-file.txt'
    sentinel.write_text('keep')
    monkeypatch.setattr(encoding,'ffmpeg_executable',lambda: '/usr/bin/ffmpeg')
    frames = (Image.new('RGB',(32,18),'red') for _ in range(1 if failure=='frames' else 2))
    if failure=='space':
        monkeypatch.setattr(encoding.shutil,'disk_usage',lambda _: SimpleNamespace(free=0))
    if failure=='encoder':
        monkeypatch.setattr(encoding.subprocess,'run',lambda *a,**kw: SimpleNamespace(returncode=1))
    if failure=='timeout':
        def timeout(*args,**kwargs):
            raise subprocess.TimeoutExpired('ffmpeg',900)
        monkeypatch.setattr(encoding.subprocess,'run',timeout)
    if failure=='busy':
        encoding._gate.acquire()
    try:
        with pytest.raises((RuntimeError,ValueError)):
            encoding.encode_frames(frames,width=32,height=18,frame_count=2,seconds=2,image_format='webp')
    finally:
        if failure=='busy':
            encoding._gate.release()
    assert not encoding._gate.locked()
    assert list((storage/'temp').iterdir()) == [sentinel]


def test_atomic_latest_cover_preserves_old_file_on_failure(storage,monkeypatch):
    path = encoding.save_cover(b'old',server='server',library='../4',image_format='jpeg')
    assert path.parent == storage/'output'
    assert encoding.save_cover(b'new',server='server',library='../4',image_format='jpeg') == path
    assert path.read_bytes() == b'new'
    def fail(*args):
        raise OSError('replace failed')
    monkeypatch.setattr(encoding.os,'replace',fail)
    with pytest.raises(OSError):
        encoding.save_cover(b'broken',server='server',library='../4',image_format='jpeg')
    assert path.read_bytes() == b'new'
    assert list(path.parent.iterdir()) == [path]


def test_encoder_uses_image_absolute_path_not_path_lookup(monkeypatch):
    from pathlib import Path
    assert encoding.FFMPEG_EXECUTABLE.as_posix() == '/usr/bin/ffmpeg'
    monkeypatch.setattr(Path,'is_file',lambda self: True)
    monkeypatch.setattr(encoding.os,'access',lambda *args: True)
    def forbidden(*args):
        pytest.fail('Must not search PATH')
    monkeypatch.setattr(shutil,'which',forbidden)
    assert encoding.ffmpeg_executable().replace('\\','/') == '/usr/bin/ffmpeg'
    monkeypatch.setattr(encoding.os,'access',lambda *args: False)
    with pytest.raises(RuntimeError,match='/usr/bin/ffmpeg'):
        encoding.ffmpeg_executable()


def test_preview_job_survives_module_reload(monkeypatch):
    from cinecircuit_plugins.media_cover_generator import preview
    async def fake(*args):
        await asyncio.sleep(0)
        return {'width':1920,'height':1080,'image_words':[123],'byte_length':4}
    monkeypatch.setattr(preview,'render_preview',fake)
    async def check():
        identity = preview.start_preview(None,{},None)['preview_id']
        with pytest.raises(ValueError):
            preview.start_preview(None,{},None)
        assert preview.preview_status(identity)['status']=='rendering'
        jobs = preview._jobs
        await jobs[identity]
        importlib.reload(preview)
        assert preview.preview_status(identity)['width']==1920
        jobs.clear()
    asyncio.run(check())
