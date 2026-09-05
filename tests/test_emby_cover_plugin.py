from __future__ import annotations

import asyncio
import base64
import io
import logging
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from app.modules.media.media_server_service import MediaServerService
from cinecircuit_plugins.media_cover_generator import (
    LibraryArtworkPlugin,
)
from cinecircuit_plugins.media_cover_generator import plugin as cover_plugin_module
from cinecircuit_plugins.media_cover_generator.renderer import (
    CoverRenderer,
    CoverRenderOptions,
)
from app.modules.plugins.permissions import PluginPermission
from cinecircuit_plugins.catalog import test_registry as PluginRegistry
from app.modules.plugins.contracts import PluginApiRequest


@pytest.fixture(autouse=True)
def local_windows_encoder(monkeypatch):
    import os
    import shutil
    from pathlib import Path
    if os.name == 'nt' and (executable := shutil.which('ffmpeg')):
        from cinecircuit_plugins.media_cover_generator import encoding
        monkeypatch.setattr(encoding,'FFMPEG_EXECUTABLE',Path(executable))


def jpeg(color: tuple[int, int, int], size: tuple[int, int] = (720, 1080)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, "JPEG", quality=90)
    return output.getvalue()


@pytest.mark.parametrize(
    "style", ["spotlight", "split", "mosaic", "mosaic_focus", "triptych", "filmstrip", "diagonal", "duo", "stack", "editorial", "panorama", "cinema"]
)
def test_original_cover_renderer_outputs_valid_jpeg(style: str) -> None:
    source = [jpeg((30 + index * 15, 70 + index * 10, 120)) for index in range(8)]

    result = CoverRenderer().render(
        source,
        title="华语电影",
        subtitle="EMBY MOVIES",
        item_count=128,
        options=CoverRenderOptions(style=style, width=854, height=480, blur_radius=8),
    )

    with Image.open(io.BytesIO(result)) as image:
        assert image.format == "JPEG"
        assert image.size == (854, 480)


def test_overlay_preserves_upper_images_and_has_no_horizontal_seam():
    image=Image.new("RGBA",(400,240),(220,220,220,255))
    CoverRenderer._draw_background_overlay(image)
    assert image.getpixel((10,40)) == (220,220,220,255)
    assert image.getpixel((350,210)) == (220,220,220,255)
    column=[image.getpixel((30,y))[0] for y in range(240)]
    assert max(abs(a-b) for a,b in zip(column,column[1:])) <= 4
    assert image.getpixel((30,210))[0] < 140


def test_zero_blur_and_new_style_configuration_are_preserved():
    options=CoverRenderOptions.from_config({'blur_radius':0,'style':'diagonal'})
    assert options.blur_radius==0
    assert options.style=='diagonal'


@pytest.mark.parametrize('style',['diagonal','duo','stack','editorial','panorama','cinema'])
def test_new_styles_are_available_in_schema_and_generation(style):
    plugin=LibraryArtworkPlugin()
    fields={f['key']:f for f in plugin.manifest.to_dict()['config_schema']['fields']}
    assert style in {o['value'] for o in fields['cover_style_base']['options']}
    run=cover_plugin_module.ArtworkGenerationRun(plugin,SimpleNamespace(config={'cover_style_base':style}))
    assert run.options.style==style


def test_animation_holds_clear_frames_and_text_stays_opaque():
    first=Image.new('RGBA',(32,18),(255,0,0,255))
    second=Image.new('RGBA',(32,18),(0,0,255,255))
    frames=CoverRenderer._blended_animation_frames([first,second],16)
    assert all(frame.getpixel((0,0))==(255,0,0,255) for frame in frames[:7])
    assert frames[7].getpixel((0,0)) not in [(255,0,0,255),(0,0,255,255)]
    renderer=CoverRenderer()
    renderer._draw_copy(first,title='A',subtitle='LONG ENGLISH TITLE',item_count=128,
                        options=CoverRenderOptions(width=32,height=18),accent=(80,90,100))
    assert first.getchannel('A').getextrema()==(255,255)


def test_shadow_opacity_is_not_replaced_by_opaque_card_mask():
    canvas=Image.new('RGBA',(100,100),(255,255,255,255))
    CoverRenderer._paste_shadow(canvas,Image.new('RGBA',(20,20),(255,255,255,255)),(30,30),5)
    assert canvas.getpixel((53,45))[0] >= 195


def test_font_fit_limits_long_subtitle_width_and_height():
    from PIL import ImageDraw
    renderer=CoverRenderer()
    text='INTERNATIONAL MOVIE COLLECTION'
    font=renderer._fit_font(text,240,220,bold=False,preset='editorial',max_height=30)
    box=ImageDraw.Draw(Image.new('RGB',(1,1))).textbbox((0,0),text,font=font)
    assert box[2]-box[0] <= 220
    assert box[3]-box[1] <= 30


def test_material_and_background_controls_change_actual_renderer_output():
    from PIL import ImageDraw
    source=Image.new('RGB',(360,540),'#d07030')
    ImageDraw.Draw(source).rectangle((0,0,160,260),fill='#2070d0')
    output=io.BytesIO()
    source.save(output,'JPEG')
    renderer=CoverRenderer()
    base={'style':'duo','width':640,'height':360,'show_count':False}
    backgrounds=[]
    for mode,blur in [('solid',0),('gradient',0),('blurred',0),('blurred',80)]:
        canvas=renderer._designed_layout([source],CoverRenderOptions(**base,background_mode=mode,blur_radius=blur),(100,90,80))
        backgrounds.append(canvas.crop((0,0,250,360)).tobytes())
    assert len(set(backgrounds))==4
    finishes=[]
    for finish in ['clean','shadow','silver']:
        finishes.append(renderer.render([output.getvalue()],title='MOVIES',subtitle='COLLECTION',item_count=1,
            options=CoverRenderOptions(**base,text_finish=finish)))
    assert len(set(finishes))==3


def test_preview_uses_current_fonts_and_background_without_saving(monkeypatch):
    from pathlib import Path
    from cinecircuit_plugins.media_cover_generator.preview import render_preview
    seen=[]
    original=CoverRenderer.render
    def record(self,sources,**kwargs):
        seen.append(kwargs['options'])
        return original(self,sources,**kwargs)
    monkeypatch.setattr(CoverRenderer,'render',record)
    config={'cover_style_base':'diagonal','resolution':'custom','custom_width':7680,'custom_height':4320,
            'zh_font_preset':'serif','en_font_preset':'editorial','zh_font_size':130,'en_font_size':55,
            'blur_radius':0,'background_mode':'blurred','text_finish':'silver'}
    result=asyncio.run(render_preview(LibraryArtworkPlugin(),config,CoverRenderer.system_cjk_font() or Path('')))
    assert result['width']==1920 and result['height']==1080
    assert result['mime']=='image/jpeg'
    assert result['image_words'][0].to_bytes(4,'little').startswith(b'\xff\xd8')
    assert seen[0].zh_font_preset=='serif' and seen[0].en_font_preset=='editorial'
    assert seen[0].zh_font_size==130 and seen[0].en_font_size==55
    assert seen[0].blur_radius==0 and seen[0].text_finish=='silver'
    assert config['custom_width']==7680


def test_media_server_cover_api_keeps_credentials_in_host_gateway() -> None:
    downloaded = jpeg((22, 66, 110))
    uploaded = jpeg((110, 44, 66), (854, 480))
    requests: list[httpx.Request] = []

    class Config:
        def get_media_servers(self, redact: bool = True) -> dict:
            assert redact is False
            return {
                "active_id": "emby-1",
                "items": [
                    {
                        "uid": "emby-1",
                        "name": "家庭 Emby",
                        "provider": "emby",
                        "enabled": True,
                        "config": {
                            "base_url": "http://emby.local:8096",
                            "api_key": "secret-token",
                        },
                    }
                ],
            }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["X-Emby-Token"] == "secret-token"
        assert request.url.params["api_key"] == "secret-token"
        if request.url.path == "/Library/VirtualFolders/Query":
            return httpx.Response(
                200,
                json={
                    "Items": [{"ItemId": "library-1", "Name": "电影", "CollectionType": "movies"}]
                },
            )
        if request.url.path == "/Items":
            assert request.url.params["ParentId"] == "library-1"
            assert request.url.params["IncludeItemTypes"] == "Movie"
            return httpx.Response(
                200,
                json={
                    "TotalRecordCount": 42,
                    "Items": [
                        {
                            "Id": "movie-1",
                            "Name": "演示电影",
                            "Type": "Movie",
                            "ImageTags": {"Primary": "tag-1"},
                            "BackdropImageTags": ["tag-2"],
                        }
                    ],
                },
            )
        if request.method == "GET" and request.url.path == "/Items/movie-1/Images/Backdrop/0":
            return httpx.Response(200, content=downloaded, headers={"Content-Type": "image/jpeg"})
        if request.method == "POST" and request.url.path == "/Items/library-1/Images/Primary":
            assert request.headers["Content-Type"] == "image/jpeg"
            assert base64.b64decode(request.content) == uploaded
            return httpx.Response(204)
        return httpx.Response(404)

    service = MediaServerService(Config(), transport=httpx.MockTransport(handler))

    async def scenario() -> None:
        libraries = await service.list_libraries()
        assert libraries == {
            "server_id": "emby-1",
            "server_name": "家庭 Emby",
            "items": [{"id": "library-1", "name": "电影", "collection_type": "movies"}],
        }
        listing = await service.list_library_items(
            "emby-1",
            "library-1",
            include_types=["Movie"],
        )
        assert listing["total"] == 42
        assert listing["items"][0]["backdrop_count"] == 1
        assert await service.get_item_image("emby-1", "movie-1", "Backdrop") == downloaded
        result = await service.set_primary_image("emby-1", "library-1", uploaded)
        assert result["bytes"] == len(uploaded)

    asyncio.run(scenario())
    assert len(requests) == 4


def test_emby_cover_plugin_previews_updates_and_skips_unchanged(monkeypatch) -> None:
    source = [jpeg((30 + index * 20, 80, 140)) for index in range(8)]

    class MediaServers:
        def __init__(self) -> None:
            self.uploads: list[bytes] = []

        async def configurations(self):
            return {'items':[{'id':'emby-1','type':'emby','enabled':True}]}

        async def libraries(self, server_id: str = "") -> dict:
            return {
                "server_id": "emby-1",
                "server_name": "家庭 Emby",
                "items": [{"id": "library-1", "name": "华语电影", "collection_type": "movies"}],
            }

        async def library_items(self, server_id, library_id, *, limit, include_types) -> dict:
            assert server_id == "emby-1"
            assert library_id == "library-1"
            assert include_types == ("Movie",)
            return {
                "total": 88,
                "items": [
                    {"id": f"movie-{index}", "has_primary": True, "backdrop_count": 1}
                    for index in range(8)
                ],
            }

        async def item_image(self, server_id, item_id, image_type, *, index=0) -> bytes:
            return source[int(item_id.split("-")[-1])]

        async def set_primary_image(self, server_id, item_id, content, *, content_type) -> dict:
            assert content_type == "image/jpeg"
            self.uploads.append(content)
            return {"ok": True}

    class Items:
        def __init__(self) -> None:
            self.values: dict[str, dict] = {}

        def get(self, key: str) -> dict | None:
            return self.values.get(key)

        def record(self, key, status, *, payload=None, result=None) -> dict:
            value = {
                "item_key": key,
                "status": status,
                "payload": payload or {},
                "result": result or {},
            }
            self.values[key] = value
            return value

    media_servers = MediaServers()
    items = Items()

    def context(*, dry_run: bool):
        return SimpleNamespace(
            config={
                "selected_servers": ["emby-1"],
                "dry_run": dry_run,
                "style": "mosaic",
                "resolution": "480p",
                "source_limit": 8,
                "title_map": {"华语电影": {"title": "华语电影", "subtitle": "CINEMA"}},
            },
            media_servers=media_servers,
            items=items,
            logger=logging.getLogger("test.emby-cover"),
        )

    plugin = LibraryArtworkPlugin()

    async def skip_font_download(_context):
        return None

    monkeypatch.setattr(plugin, "_ensure_cjk_font", skip_font_download)
    preview = asyncio.run(plugin.run(context(dry_run=True)))
    updated = asyncio.run(plugin.run(context(dry_run=False)))
    unchanged = asyncio.run(plugin.run(context(dry_run=False)))

    assert preview["preview_count"] == 1
    assert preview["updated_count"] == 0
    assert updated["updated_count"] == 1
    assert len(media_servers.uploads) == 1
    assert unchanged["unchanged_count"] == 1
    assert len(media_servers.uploads) == 1


def test_emby_cover_font_is_downloaded_once_to_persistent_cache(tmp_path, monkeypatch) -> None:
    content = b"test-cjk-font"
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, content=content, request=request)

    def client(*_args, **_kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(CoverRenderer, "system_cjk_font", staticmethod(lambda: None))
    monkeypatch.setattr(
        cover_plugin_module,
        "get_settings",
        lambda: SimpleNamespace(config_dir=str(tmp_path)),
    )
    monkeypatch.setattr(cover_plugin_module, "outbound_async_client", client)

    plugin = LibraryArtworkPlugin()
    plugin.FONT_SHA256 = sha256(content).hexdigest()
    context = SimpleNamespace(logger=logging.getLogger("test.emby-cover.font"))
    first = asyncio.run(plugin._ensure_cjk_font(context))
    second = asyncio.run(plugin._ensure_cjk_font(context))

    assert first == second
    assert first.read_bytes() == content
    assert requests == 1


def test_emby_cover_plugin_is_registered_with_explicit_write_permission() -> None:
    catalog = {item["id"]: item for item in PluginRegistry().builtin_catalog()}
    manifest = catalog["emby-cover-generator"]

    assert manifest["schedule_seconds"] == 24 * 60 * 60
    assert manifest["permissions"] == [
        PluginPermission.MEDIA_SERVER_READ,
        PluginPermission.MEDIA_SERVER_WRITE_IMAGES,
    ]
    fields = {field["key"]: field for field in manifest["config_schema"]["fields"]}
    assert fields["zh_font_preset"]["input_type"] == "select"
    assert [option["value"] for option in fields["zh_font_preset"]["options"]] == [
        "wendao", "cuyasong",
        "modern",
        "bold",
        "serif",
    ]
    assert fields["en_font_preset"]["input_type"] == "select"
    assert [option["value"] for option in fields["en_font_preset"]["options"]] == [
        "emblemaone", "melete", "phosphate", "josefinsans", "lilitaone", "monoton", "plaster",
        "inter",
        "cinema",
        "editorial",
    ]
    assert manifest["config_schema"]["fields"][-1] == {
        "key": "dry_run",
        "input_type": "switch",
        "label": "预览模式（不上传）",
        "default": False,
        "section": "run",
    }


def test_emby_cover_disabled_schedule_skips_but_manual_generate_runs(monkeypatch) -> None:
    runs = 0

    async def fake_run(_self) -> dict[str, str]:
        nonlocal runs
        runs += 1
        return {"status": "generated"}

    monkeypatch.setattr(cover_plugin_module.ArtworkGenerationRun, "run", fake_run)
    plugin = LibraryArtworkPlugin()
    scheduled_context = SimpleNamespace(
        trigger="scheduled",
        config={"enabled": False},
    )
    manual_context = SimpleNamespace(
        trigger="manual",
        config={"enabled": False},
    )

    skipped = asyncio.run(plugin.run(scheduled_context))
    generated = asyncio.run(
        plugin.handle_api(
            PluginApiRequest(action="generate", method="POST"),
            manual_context,
        )
    )

    assert skipped == {
        "status": "skipped",
        "reason": "scheduled_generation_disabled",
    }
    assert generated == {"status": "generated"}
    assert runs == 1


def test_renderer_is_not_imported_at_module_level():
    import ast
    from pathlib import Path
    import cinecircuit_plugins.media_cover_generator.plugin as module
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    assert not any(isinstance(node, ast.ImportFrom) and node.module == "renderer" for node in tree.body)


def test_default_fonts_are_real_requested_families_and_saved_choices_survive():
    options = CoverRenderOptions.from_config({})
    assert (options.zh_font_preset, options.en_font_preset) == ('wendao', 'emblemaone')
    renderer = CoverRenderer()
    assert renderer._font(80, bold=True, preset='wendao').getname()[0] == 'WDCH'
    assert renderer._font(80, bold=False, preset='emblemaone').getname()[0] == 'Emblema One'
    custom = CoverRenderOptions.from_config({'zh_font_preset':'serif','en_font_preset':'monoton'})
    assert (custom.zh_font_preset, custom.en_font_preset) == ('serif', 'monoton')


@pytest.mark.parametrize('preset,family', [('cuyasong','FZYaSongS-B-GB'),('phosphate','PhosphateSolid'),('melete','Melete'),('josefinsans','Josefin Sans'),('lilitaone','Lilita One'),('monoton','Monoton'),('plaster','Plaster')])
def test_named_presets_load_exact_family(preset, family):
    assert CoverRenderer()._font(50, bold=False, preset=preset).getname()[0] == family


def test_full_size_sample_is_original_and_rejects_arbitrary_paths():
    from pathlib import Path
    from cinecircuit_plugins.media_cover_generator.preview import read_sample
    sample = read_sample('diagonal', '1')
    original = Path(cover_plugin_module.__file__).parent / 'assets' / 'sample-diagonal.jpg'
    from app.core.task_failures import redact_sensitive_data
    transported = redact_sensitive_data(sample, secret_values=('abc',))
    assert bytes(transported['image_bytes']) == original.read_bytes()
    with pytest.raises(ValueError):
        read_sample('../../plugin', '1')


@pytest.mark.parametrize('height', [540,1080])
def test_new_layout_accent_is_vertical_beside_subtitle(height):
    renderer=CoverRenderer()
    width=round(height*16/9)
    options=CoverRenderOptions(style='stack',width=width,height=height,show_count=False,text_finish='clean')
    canvas=Image.new('RGBA',(width,height),(0,0,0,0))
    accent=(180,90,40)
    renderer._draw_copy(canvas,title='华语电影',subtitle='MOVIE',item_count=0,options=options,accent=accent)
    margin=int(width*.065)
    baseline=int(height*.45)
    unit=max(1,round(height/1080))
    assert canvas.getpixel((margin+4,baseline-19*unit))[3]==0
    color=(*renderer._brighten(accent),255)
    ys=[y for y in range(baseline,height) if canvas.getpixel((margin+1,y))==color]
    assert ys and max(ys)-min(ys)>round(22*height/1080)*2
    assert max(ys)-min(ys)<height*.15
    empty=Image.new('RGBA',(width,height),(0,0,0,0))
    renderer._draw_copy(empty,title='华语电影',subtitle='',item_count=0,options=options,accent=accent)
    assert empty.getpixel((margin+1,ys[len(ys)//2]))[3]==0


def test_all_shipped_sample_styles_disable_count_badges(tmp_path,monkeypatch):
    import json,runpy
    from pathlib import Path
    script=Path(__file__).resolve().parents[1]/'scripts/render_cover_samples.py'
    namespace=runpy.run_path(str(script))
    main=namespace['main']
    globals_=main.__globals__
    seen=[]
    class SampleRenderer:
        def render(self,*args,**kwargs):
            seen.append(kwargs['options'])
            return jpeg((30,40,50),(64,36))
        render_animated=render
    (tmp_path/'sample-sources.json').write_text(json.dumps([{'id':1}]))
    monkeypatch.setitem(globals_,'ASSETS',tmp_path)
    monkeypatch.setitem(globals_,'CACHE',tmp_path/'cache')
    monkeypatch.setitem(globals_,'source',lambda movie:jpeg((20,30,40)))
    monkeypatch.setitem(globals_,'CoverRenderer',SampleRenderer)
    main()
    assert len(seen)==17
    assert all(not options.show_count for options in seen)


@pytest.mark.parametrize('style',['spotlight','split','mosaic','mosaic_focus','triptych','filmstrip','diagonal','duo','stack','editorial','panorama','cinema'])
def test_every_style_uses_one_vertical_subtitle_bar(style, monkeypatch):
    from PIL import ImageDraw
    rectangles=[]
    original=ImageDraw.ImageDraw.rectangle
    def record(self,xy,*args,**kwargs):
        rectangles.append(xy)
        return original(self,xy,*args,**kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw,'rectangle',record)
    renderer=CoverRenderer()
    options=CoverRenderOptions(style=style,width=960,height=540,show_count=False)
    renderer._draw_copy(Image.new('RGBA',(960,540)),title='电影典藏',subtitle='MOVIE COLLECTION',item_count=0,options=options,accent=(180,90,40))
    assert len(rectangles)==1
    x0,y0,x1,y1=rectangles[0]
    assert y1-y0>x1-x0
    assert y1<540


def test_animation_uses_filmstrip_typography_and_preserves_empty_subtitle(monkeypatch):
    seen=[]
    monkeypatch.setattr(CoverRenderer,'_draw_copy',lambda self,canvas,**kwargs:seen.append(kwargs))
    CoverRenderer().render_animated([jpeg((30,40,50))],title='电影',subtitle='',item_count=0,
                                  options=CoverRenderOptions(width=320,height=180),image_format='webp',duration_seconds=2,frames_per_second=1)
    assert seen and all(item['options'].style=='filmstrip' and item['subtitle']=='' for item in seen)


@pytest.mark.parametrize('format_name',['webp','apng','gif'])
def test_moving_wall_keeps_left_copy_and_background_fixed(format_name,monkeypatch):
    from PIL import ImageChops
    frames=[]
    from cinecircuit_plugins.media_cover_generator import encoding
    original=encoding.encode_frames
    def capture(source,**kwargs):
        def recorded():
            for canvas in source:
                frames.append(canvas.copy())
                yield canvas
        return original(recorded(),**kwargs)
    monkeypatch.setattr(encoding,'encode_frames',capture)
    data=CoverRenderer().render_animated([jpeg((20+i*25,60+i*15,120)) for i in range(8)],title='电影典藏',subtitle='MOVIE',item_count=0,
         options=CoverRenderOptions(style='diagonal',width=320,height=180,show_count=False),image_format=format_name,duration_seconds=2,frames_per_second=4)
    with Image.open(io.BytesIO(data)) as image:
        assert image.n_frames>1 and image.size==(320,180)
    assert len(frames)==8
    for frame in frames[1:]:
        assert frame.crop((0,0,125,180)).tobytes()==frames[0].crop((0,0,125,180)).tobytes()
    assert frames[0].crop((170,0,320,180)).tobytes()!=frames[1].crop((170,0,320,180)).tobytes()


def test_moving_wall_loop_and_plugin_route():
    from cinecircuit_plugins.media_cover_generator.plugin import ArtworkGenerationRun
    renderer=CoverRenderer()
    images=[Image.new('RGB',(60,90),(i*25,60,100)) for i in range(8)]
    options=CoverRenderOptions(style='diagonal',width=320,height=180)
    assert renderer._designed_layout(images,options,(40,60,100),scroll_phase=0).tobytes()==renderer._designed_layout(images,options,(40,60,100),scroll_phase=1).tobytes()
    run=ArtworkGenerationRun(LibraryArtworkPlugin(),SimpleNamespace(config={'cover_style_base':'animated_diagonal'}))
    assert run.animated and run.options.style=='diagonal'


def test_matte_controls_are_independent_and_deterministic():
    from dataclasses import replace
    renderer = CoverRenderer()
    image = Image.new('RGB',(160,90),(75,90,110))
    options = CoverRenderOptions(width=320,height=180,background_color='#506478',background_grain=0,background_light=0)
    flat = renderer._paper_background(image,options,(80,100,120))
    grain = renderer._paper_background(image,replace(options,background_grain=5),(80,100,120))
    assert grain.tobytes() == renderer._paper_background(image,replace(options,background_grain=5),(80,100,120)).tobytes()
    assert flat.tobytes()!=grain.tobytes()
    light = renderer._paper_background(image,replace(options,background_light=60),(80,100,120))
    assert sum(light.getpixel((310,80))[:3]) > sum(light.getpixel((1,80))[:3])
    zero = renderer._paper_background(image,replace(options,background_mix=0),(80,100,120))
    full = renderer._paper_background(image,replace(options,background_mix=100),(80,100,120))
    assert zero.getpixel((100,80))[:3] == (75,90,110)
    assert full.getpixel((100,80))[:3] == (80,100,120)


@pytest.mark.parametrize('direction',['up','down','alternate'])
def test_each_scroll_direction_loops_and_leaves_matte_fixed(direction):
    renderer = CoverRenderer()
    images = [Image.new('RGB',(60,90),(30+i*25,80,100)) for i in range(8)]
    options = CoverRenderOptions(style='diagonal',width=320,height=180,animation_direction=direction,background_grain=8)
    frames = [renderer._designed_layout(images,options,(70,90,110),scroll_phase=p) for p in (0,.2,1)]
    assert frames[0].tobytes()==frames[2].tobytes()
    assert frames[0].crop((0,0,125,180)).tobytes()==frames[1].crop((0,0,125,180)).tobytes()
    assert frames[0].tobytes()!=frames[1].tobytes()


@pytest.mark.parametrize('style',['echo','wedge'])
def test_new_templates_have_real_titles_and_preserve_clear_photos(style):
    from dataclasses import replace
    renderer=CoverRenderer()
    options=CoverRenderOptions(style=style,width=640,height=360,show_count=False)
    images=[Image.new('RGB',(240,360),(200,100,50))]
    before=renderer._designed_layout(images,options,(120,100,70))
    other=renderer._designed_layout(images,replace(options,background_grain=10,background_light=90),(120,100,70))
    assert before.getpixel((430,190))==other.getpixel((430,190))
    after=before.copy()
    renderer._draw_copy(after,title='电影典藏',subtitle='MOVIE COLLECTION',item_count=0,options=options,accent=(120,100,70))
    assert before.crop((0,120,240,320)).tobytes()!=after.crop((0,120,240,320)).tobytes()
    run=cover_plugin_module.ArtworkGenerationRun(LibraryArtworkPlugin(),SimpleNamespace(config={'cover_style_base':style}))
    assert run.options.style==style


def test_subtitle_wrap_and_material_are_shared(monkeypatch):
    renderer=CoverRenderer()
    lines,font,line_height,gap=renderer._subtitle_lines('MOVIE COLLECTION',75,630,250,'emblemaone')
    assert lines==['MOVIE','COLLECTION']
    assert font.size==75 and line_height*2+gap<=250
    seen=[]
    original=renderer._draw_title_material
    def record(layer,position,text,font,finish,shadow_color):
        seen.append((text,finish,shadow_color))
        original(layer,position,text,font,finish,shadow_color)
    monkeypatch.setattr(renderer,'_draw_title_material',record)
    renderer._draw_copy(Image.new('RGBA',(640,360)),title='电影',subtitle='MOVIE',item_count=0,
                        options=CoverRenderOptions(style='echo',width=640,height=360,show_count=False,text_finish='silver'),accent=(100,80,60))
    assert len(seen)==2 and all(item[1]=='silver' for item in seen)
    assert seen[0][2]==seen[1][2]==(28,22,17)


def test_dynamic_options_preserve_all_new_controls():
    config={'cover_style_base':'animated_diagonal','background_grain':0,'background_mix':12,'background_light':67,'animation_direction':'alternate'}
    run=cover_plugin_module.ArtworkGenerationRun(LibraryArtworkPlugin(),SimpleNamespace(config=config))
    assert (run.options.background_grain,run.options.background_mix,run.options.background_light,run.options.animation_direction)==(0,12,67,'alternate')


def test_large_animation_preview_preserves_selected_resolution(monkeypatch):
    from cinecircuit_plugins.media_cover_generator.preview import render_preview
    calls=[]
    def fake(self,sources,**kwargs):
        calls.append(kwargs['options'])
        return b'x'*4_900_000 if len(calls)==1 else b'preview'
    monkeypatch.setattr(CoverRenderer,'render_animated',fake)
    config={'cover_style_base':'animated_diagonal','animation_resolution':'640x360','animation_direction':'down'}
    result=asyncio.run(render_preview(LibraryArtworkPlugin(),config,None))
    assert [(x.width,x.height) for x in calls]==[(640,360)]
    assert result['width']==640 and result['height']==360
    assert result['byte_length']==4_900_000
    assert len(result['image_words'])==1_225_000
    assert config['animation_resolution']=='640x360'
    assert all(x.animation_direction=='down' for x in calls)


@pytest.mark.parametrize('style',['animated','animated_diagonal'])
def test_animation_preview_obeys_configured_timing(monkeypatch,style):
    from cinecircuit_plugins.media_cover_generator.preview import render_preview
    calls=[]
    def fake(self,sources,**kwargs):
        calls.append(kwargs)
        return b'preview'
    monkeypatch.setattr(CoverRenderer,'render_animated',fake)
    asyncio.run(render_preview(LibraryArtworkPlugin(),{'cover_style_base':style,'animation_fps':24,'animation_duration':10},None))
    assert calls[0]['frames_per_second']==24
    assert calls[0]['duration_seconds']==10


def test_carousel_has_many_transition_frames(monkeypatch):
    from cinecircuit_plugins.media_cover_generator import encoding
    frames=[]
    def capture(source,**kwargs):
        frames.extend(frame.tobytes() for frame in source)
        return b'encoded'
    monkeypatch.setattr(encoding,'encode_frames',capture)
    CoverRenderer().render_animated([jpeg((220,20,10)),jpeg((10,40,220))],title='',subtitle='',item_count=0,
        options=CoverRenderOptions(width=320,height=180,show_count=False),image_format='webp',duration_seconds=6,frames_per_second=12)
    assert len(frames)==72
    assert len(set(frames))>=40
