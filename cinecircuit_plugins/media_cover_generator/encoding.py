"""Independent disk-backed animation encoder. No third-party compositor code."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from collections.abc import Iterable

from PIL import Image

from .runtime_state import state

_gate = state.gate
# The host media gateway accepts at most 20 MiB per cover.
MAX_FILE_BYTES = 20 * 1024 * 1024
FFMPEG_EXECUTABLE = Path('/usr/bin/ffmpeg')


def ffmpeg_executable() -> str:
    # Use the image-owned binary, never PATH or a writable plugin/config folder.
    if not FFMPEG_EXECUTABLE.is_file() or not os.access(FFMPEG_EXECUTABLE, os.X_OK):
        raise RuntimeError('镜像内 /usr/bin/ffmpeg 缺失或不可执行，请更新到内置 FFmpeg 的镜像')
    return str(FFMPEG_EXECUTABLE)


def cover_directory() -> Path:
    from app.core.config import get_settings
    base = Path(get_settings().config_dir) / 'plugins'
    root = base / 'covers'
    if not root.resolve().is_relative_to(base.resolve()):
        raise ValueError('封面目录不能指向插件目录之外')
    root.mkdir(parents=True, exist_ok=True)
    for name in ('temp', 'output'):
        child = root / name
        if child.is_symlink() or not child.resolve().is_relative_to(root.resolve()):
            raise ValueError('封面子目录不能是外部链接')
        child.mkdir(exist_ok=True)
    return root


def save_cover(data: bytes, *, server: str, library: str, image_format: str) -> Path:
    suffix = {'jpeg':'jpg', 'apng':'png', 'gif':'gif', 'webp':'webp'}[image_format]
    folder = cover_directory() / 'output'
    identity = hashlib.sha256(f'{server}\0{library}'.encode()).hexdigest()[:24]
    # One latest result per server/library/format. Existing result survives failures.
    target = folder / f'{identity}.{suffix}'
    fd, name = tempfile.mkstemp(prefix='.cover-', suffix='.tmp', dir=folder)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name,target)
    finally:
        Path(name).unlink(missing_ok=True)
    return target


def encode_frames(frames: Iterable[Image.Image], *, width: int, height: int,
                  frame_count: int, seconds: int, image_format: str) -> bytes:
    executable = ffmpeg_executable()
    if image_format not in {'apng','webp','gif'}:
        raise ValueError('不支持的动态格式')
    if not (2 <= frame_count <= 500 and 1 <= width <= 1920 and 1 <= height <= 1080 and 2 <= seconds <= 60):
        raise ValueError('动态封面最多 1080p、500 帧')
    if not _gate.acquire(blocking=False):
        raise RuntimeError('已有封面正在编码，请等待完成后重试')
    try:
        root = cover_directory() / 'temp'
        required = width * height * 3 * frame_count + 256*1024*1024
        if shutil.disk_usage(root).free < required:
            raise RuntimeError('封面临时目录剩余空间不足，请清理空间或缩短动画')
        # This unique directory is the only recursive cleanup target. No output
        # directory, user files or other active task directories are ever removed.
        with tempfile.TemporaryDirectory(prefix='encode-',dir=root) as work:
            folder = Path(work)
            written = 0
            first_digest = None
            identical = True
            for index, frame in enumerate(frames):
                if index >= frame_count or frame.size != (width,height):
                    raise ValueError('动画帧数量或尺寸异常')
                rgb = frame.convert('RGB')
                if identical:
                    digest = hashlib.sha256(rgb.tobytes()).digest()
                    if first_digest is None:
                        first_digest = digest
                    identical = digest == first_digest
                rgb.save(folder/f'{index:05d}.bmp',format='BMP')
                written += 1
            if written != frame_count:
                raise ValueError('动画帧生成不完整')
            # No shell, no user-controlled arguments or executable path.
            common = [executable,'-hide_banner','-loglevel','error','-nostdin','-y',
                      '-threads','2','-filter_threads','1','-filter_complex_threads','1',
                      '-framerate',f'{frame_count}/{seconds}','-i',str(folder/'%05d.bmp')]
            def run(command):
                with tempfile.TemporaryFile(dir=folder) as log:
                    try:
                        result = subprocess.run(command,stdout=subprocess.DEVNULL,stderr=log,timeout=900,check=False)
                    except subprocess.TimeoutExpired:
                        raise RuntimeError('动态编码超时，临时帧已清理') from None
                    if result.returncode:
                        raise RuntimeError('FFmpeg 编码失败，原有成品未改动')
            if image_format == 'gif':
                # Two passes avoid keeping an entire split stream buffered in RAM.
                palette = folder/'palette.png'
                run(common+['-vf','palettegen=max_colors=256','-frames:v','1','-threads','2',str(palette)])
                command = common+['-i',str(palette),'-lavfi','paletteuse=dither=bayer:bayer_scale=3',
                                  '-loop','0','-f','gif']
            elif image_format == 'webp':
                command = common+['-c:v','libwebp_anim','-quality','88','-compression_level','3','-loop','0','-f','webp']
            else:
                command = common+['-c:v','apng','-pix_fmt','rgb24','-plays','0','-f','apng']
            output = folder/'encoded.bin'
            run(command+['-threads','2','-fs',str(MAX_FILE_BYTES+1024*1024),str(output)])
            if not output.is_file() or output.stat().st_size>MAX_FILE_BYTES:
                raise RuntimeError('动图超过宿主 20 MB 上传上限，请缩短时长或改用 WebP')
            # Verify complete animation before publishing or uploading anything.
            with Image.open(output) as image:
                # Encoders legitimately collapse identical input frames.
                if image.size != (width,height) or (not identical and not getattr(image,'is_animated',False)):
                    raise RuntimeError('编码结果不是完整动图')
                image.seek(image.n_frames-1)
                image.load()
            return output.read_bytes()
    finally:
        _gate.release()
