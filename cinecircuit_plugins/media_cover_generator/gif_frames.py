"""Coalesce equal GIF display frames without changing palettes or total delay."""

import hashlib
import io
import struct
from PIL import Image


def _subblocks(data, offset):
    while data[offset]:
        offset += 1 + data[offset]
    return offset + 1


def _frames(data):
    offset = 13 + (3 * (2 ** ((data[10] & 7) + 1)) if data[10] & 128 else 0)
    start, control = offset, None
    frames = []
    while data[offset] != 0x3B:
        if data[offset] == 0x21:
            if data[offset + 1] == 0xF9:
                control = offset
            offset = _subblocks(data, offset + 2)
        elif data[offset] == 0x2C:
            packed = data[offset + 9]
            offset += 10 + (3 * (2 ** ((packed & 7) + 1)) if packed & 128 else 0)
            offset = _subblocks(data, offset + 1)
            frames.append((start, offset, control))
            start, control = offset, None
        else:
            raise ValueError("Invalid encoded GIF block")
    return frames, start


def merge_identical_frames(data):
    frames, tail = _frames(data)
    if len(frames) < 2:
        return data
    kept: list[bytearray] = []
    previous = None
    last_delay = None
    last_disposal = 3
    with Image.open(io.BytesIO(data)) as image:
        for index, (start, end, control) in enumerate(frames):
            image.seek(index)
            digest = hashlib.sha256(image.convert("RGBA").tobytes()).digest()
            disposal = (data[control + 3] >> 2) & 7 if control is not None else 3
            delay = struct.unpack_from("<H", data, control + 4)[0] if control is not None else 0
            old_delay = (
                struct.unpack_from("<H", kept[-1], last_delay)[0]
                if kept and last_delay is not None
                else 0
            )
            if (
                digest == previous
                and disposal <= 1
                and last_disposal <= 1
                and last_delay is not None
                and old_delay + delay <= 65535
            ):
                struct.pack_into("<H", kept[-1], last_delay, old_delay + delay)
            else:
                kept.append(bytearray(data[start:end]))
                last_delay = control + 4 - start if control is not None else None
                last_disposal = disposal
            previous = digest
    return data[: frames[0][0]] + b"".join(kept) + data[tail:]
