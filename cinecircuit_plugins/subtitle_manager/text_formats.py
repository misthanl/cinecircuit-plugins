"""Conservative SBV/SubViewer and explicitly timed MicroDVD to SRT conversion."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


class UnsupportedSubtitle(ValueError):
    """A safe, fixed message suitable for reporting without source URLs."""


MAX_TIMESTAMP_MS = 360_000_000
SECONDS_PER_MINUTE = 60
TIMING_PARTS = 2


def stamp(ms: int) -> str:
    if ms < 0 or ms >= MAX_TIMESTAMP_MS:
        raise UnsupportedSubtitle("字幕时间超出支持范围")
    seconds, fraction = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{fraction:03}"


def time_ms(value: str) -> int:
    match = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})[.](\d{2,3})", value)
    if not match:
        raise UnsupportedSubtitle("字幕时间轴格式无效")
    h, m, s, fraction = match.groups()
    if int(m) >= SECONDS_PER_MINUTE or int(s) >= SECONDS_PER_MINUTE:
        raise UnsupportedSubtitle("字幕时间轴格式无效")
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(fraction.ljust(3, "0"))


def srt(cues: list[tuple[int, int, str]]) -> str:
    if not cues:
        raise UnsupportedSubtitle("未找到有效字幕时间轴")
    output = []
    for index, (start, end, text) in enumerate(cues, 1):
        if end <= start or not text.strip():
            raise UnsupportedSubtitle("字幕时间轴或正文无效")
        output.append(f"{index}\n{stamp(start)} --> {stamp(end)}\n{text.strip()}\n")
    return "\n".join(output)


def convert(text: str, extension: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if extension == "sub" and text.startswith("{"):
        return microdvd(text)
    if "[SUBTITLE]" in text:
        text = text.split("[SUBTITLE]", 1)[1].lstrip()
        # SubViewer 2 metadata applies presentation, not timing.
        while text.startswith(("[COLF]", "[STYLE]", "[SIZE]", "[FONT]")):
            text = text.partition("\n")[2].lstrip()
    cues = []
    for block in re.split(r"\n\s*\n", text):
        timing, sep, body = block.partition("\n")
        parts = timing.strip().split(",")
        if not sep or len(parts) != TIMING_PARTS:
            raise UnsupportedSubtitle("不支持的文本 SUB 类型或无效 SBV 字幕")
        cues.append((time_ms(parts[0]), time_ms(parts[1]), body.replace("[br]", "\n")))
    return srt(cues)


def microdvd(text: str) -> str:
    lines = text.splitlines()
    header = re.fullmatch(r"\{([01])\}\{\1\}([0-9]+(?:\.[0-9]+)?)", lines[0].strip())
    if not header:
        raise UnsupportedSubtitle("MicroDVD 字幕缺少有效帧率，未进行转换")
    try:
        fps = Decimal(header[2])
        if not Decimal(1) <= fps <= Decimal(240):
            raise InvalidOperation
    except InvalidOperation:
        raise UnsupportedSubtitle("MicroDVD 字幕帧率无效") from None
    cues = []
    for line in lines[1:]:
        if not line.strip():
            continue
        row = re.fullmatch(r"\{(\d{1,10})\}\{(\d{1,10})\}(.*)", line)
        if not row:
            raise UnsupportedSubtitle("MicroDVD 字幕帧时间轴无效")
        body = row[3]
        if re.search(r"\{[^}]*\}", body):
            raise UnsupportedSubtitle("暂不支持带格式控制标签的 MicroDVD 字幕")
        start, end = [
            int((Decimal(row[i]) * 1000 / fps).to_integral_value(rounding=ROUND_HALF_UP))
            for i in (1, 2)
        ]
        cues.append((start, end, body.replace("|", "\n")))
    return srt(cues)
