#!/usr/bin/env python3
"""Render a clean lyric MV from an audio file and an LRC timeline.

The LRC timestamps are assumed to start at the beginning of the song.  If the
song starts later in the supplied audio, pass that known delay with --offset.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


TIME_TAG_RE = re.compile(
    r"\[(?P<minutes>\d{1,3}):(?P<seconds>\d{1,2})(?:[\.:](?P<fraction>\d{1,3}))?\]"
)
METADATA_RE = re.compile(r"^\[(?P<key>[A-Za-z][A-Za-z0-9_-]*):(?P<value>.*)\]$")


@dataclass(frozen=True)
class LyricLine:
    start: float
    text: str


@dataclass(frozen=True)
class LrcDocument:
    metadata: dict[str, str]
    lines: list[LyricLine]
    lrc_offset_seconds: float


SUBTITLE_STYLES: dict[str, dict[str, object]] = {
    "elegant": {"bold": False, "italic": False, "outline": 2.0, "shadow": 1.0, "spacing": 1.2},
    "modern": {"bold": True, "italic": False, "outline": 1.4, "shadow": 1.0, "spacing": 0.8},
    "poster": {"bold": True, "italic": False, "outline": 3.2, "shadow": 1.6, "spacing": -0.5},
    "editorial": {"bold": False, "italic": True, "outline": 1.2, "shadow": 0.8, "spacing": 2.0},
    "ink": {"bold": False, "italic": False, "outline": 1.0, "shadow": 1.4, "spacing": 2.4},
    "mono": {"bold": True, "italic": False, "outline": 1.2, "shadow": 0.8, "spacing": 3.0},
    "outline": {"bold": True, "italic": False, "outline": 3.6, "shadow": 0.0, "spacing": 0.0, "hollow": True},
    "neon": {"bold": True, "italic": False, "outline": 1.4, "shadow": 0.0, "spacing": 0.8, "neon": True},
    "glass": {"bold": True, "italic": False, "outline": 8.0, "shadow": 0.0, "spacing": 0.8, "capsule": True},
}

MOTION_PRESETS = ("cinematic", "float", "punch", "handwritten", "neon", "minimal")


def _fraction_seconds(value: str | None) -> float:
    if not value:
        return 0.0
    return int(value) / (10 ** len(value))


def _decode_lrc(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别 LRC 文件编码：{path}")


def parse_lrc(path: Path) -> LrcDocument:
    """Parse standard LRC, including repeated timestamps and [offset:ms]."""
    metadata: dict[str, str] = {}
    parsed: list[LyricLine] = []

    for raw_line in _decode_lrc(path).splitlines():
        line = raw_line.strip()
        if not line:
            continue

        time_matches = list(TIME_TAG_RE.finditer(line))
        if not time_matches:
            metadata_match = METADATA_RE.match(line)
            if metadata_match:
                metadata[metadata_match.group("key").lower()] = metadata_match.group(
                    "value"
                ).strip()
            continue

        text = TIME_TAG_RE.sub("", line).strip()
        if not text:
            continue

        for match in time_matches:
            minutes = int(match.group("minutes"))
            seconds = int(match.group("seconds"))
            if seconds >= 60:
                raise ValueError(f"LRC 时间格式错误（秒数应小于 60）：{raw_line}")
            start = minutes * 60 + seconds + _fraction_seconds(match.group("fraction"))
            parsed.append(LyricLine(start=start, text=text))

    if not parsed:
        raise ValueError("LRC 中没有找到带时间戳的非空歌词。")

    # Python's sort is stable, so bilingual rows with the same timestamp keep
    # the author's original top-to-bottom order.
    parsed.sort(key=lambda item: item.start)

    # Collapse exact duplicate timestamps. Some exporters emit two lines at the
    # same time for bilingual lyrics; preserve both by displaying two rows.
    merged: list[LyricLine] = []
    for item in parsed:
        if merged and math.isclose(merged[-1].start, item.start, abs_tol=0.0005):
            if item.text not in merged[-1].text.split("\\N"):
                merged[-1] = LyricLine(merged[-1].start, merged[-1].text + "\\N" + item.text)
        else:
            merged.append(item)

    offset_ms = 0.0
    if "offset" in metadata:
        try:
            offset_ms = float(metadata["offset"])
        except ValueError as exc:
            raise ValueError(f"LRC 的 [offset:] 不是有效毫秒数：{metadata['offset']}") from exc

    return LrcDocument(
        metadata=metadata,
        lines=merged,
        lrc_offset_seconds=offset_ms / 1000.0,
    )


def apply_offset(lines: Iterable[LyricLine], offset_seconds: float) -> list[LyricLine]:
    shifted: list[LyricLine] = []
    for line in lines:
        start = line.start + offset_seconds
        if start < 0:
            # Negative events cannot be represented meaningfully in ASS. Clamp
            # only lines that overlap the start; this is useful for trimmed audio.
            start = 0.0
        shifted.append(LyricLine(start=start, text=line.text))
    return shifted


def _ass_timestamp(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, rem = divmod(centiseconds, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, centis = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _ass_escape(text: str) -> str:
    # Preserve our intentional bilingual line separator, but neutralize user
    # supplied ASS override blocks.
    marker = "\0LRC_LINE_BREAK\0"
    text = text.replace("\\N", marker)
    text = text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
    return text.replace(marker, r"\N")


def _ass_color(rgb: str, alpha: int = 0) -> str:
    value = rgb.strip().lstrip("#")
    if len(value) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in value):
        raise ValueError(f"颜色必须采用 #RRGGBB 格式：{rgb}")
    red, green, blue = value[0:2], value[2:4], value[4:6]
    return f"&H{alpha:02X}{blue}{green}{red}&"


def _visible_character_count(text: str) -> int:
    return len(text.replace("\\N", ""))


def _line_end(
    lines: list[LyricLine],
    index: int,
    max_duration: float,
    handoff_overlap: float = -0.02,
) -> float:
    current = lines[index]
    estimated = min(max_duration, max(2.6, 1.3 + _visible_character_count(current.text) * 0.24))
    end = current.start + estimated
    if index + 1 < len(lines):
        next_handoff = max(current.start + 0.12, lines[index + 1].start + handoff_overlap)
        if handoff_overlap >= 0:
            end = min(current.start + max_duration, next_handoff)
        else:
            end = min(end, next_handoff)
    return end


def _motion_tags(
    preset: str,
    *,
    x: int,
    y: int,
    alignment_code: int,
    duration_ms: int,
    line_index: int,
    intensity: float = 0.6,
) -> str:
    """Return ASS override tags for one continuous enter-hold-exit motion."""
    if preset not in MOTION_PRESETS:
        raise ValueError(f"未知歌词动效：{preset}")

    duration_ms = max(1, duration_ms)
    intensity = max(0.0, min(1.0, intensity))
    amplitude = 0.45 + intensity * 0.9
    if preset == "cinematic":
        enter_y = y + round(22 * amplitude)
        exit_y = y - round(12 * amplitude)
        return (
            rf"\an{alignment_code}\move({x},{enter_y},{x},{exit_y},0,{duration_ms})"
            r"\fad(220,320)\fscx97\fscy97\t(0,420,\fscx100\fscy100)\blur0.35"
        )
    if preset == "float":
        direction = 1 if line_index % 2 == 0 else -1
        enter_x = x + direction * round(30 * amplitude)
        exit_x = x - direction * round(10 * amplitude)
        return (
            rf"\an{alignment_code}\move({enter_x},{y},{exit_x},{y},0,{duration_ms})"
            r"\fad(180,260)\blur0.2"
        )
    if preset == "punch":
        start_scale = round(90 - intensity * 24)
        overshoot = round(102 + intensity * 10)
        return (
            rf"\an{alignment_code}\pos({x},{y})\fad(80,180)\fscx{start_scale}\fscy{start_scale}"
            rf"\t(0,150,\fscx{overshoot}\fscy{overshoot})\t(150,330,\fscx100\fscy100)"
        )
    if preset == "handwritten":
        enter_y = y + round(18 * amplitude)
        exit_x = x + round(6 * amplitude)
        exit_y = y - round(8 * amplitude)
        angle = round(-0.5 - intensity * 1.2, 2)
        return (
            rf"\an{alignment_code}\move({x},{enter_y},{exit_x},{exit_y},0,{duration_ms})"
            rf"\fad(240,300)\frz{angle}\t(0,450,\frz-0.25)\blur0.25"
        )
    if preset == "neon":
        blur = round(1.5 + intensity * 4.5, 2)
        start_scale = round(98 - intensity * 7)
        return (
            rf"\an{alignment_code}\pos({x},{y})\fad(260,280)\blur{blur}"
            rf"\t(0,420,\blur0.7)\fscx{start_scale}\fscy{start_scale}\t(0,420,\fscx100\fscy100)"
        )
    return rf"\an{alignment_code}\pos({x},{y})\fad(320,420)\blur0.2"


def build_ass(
    lines: list[LyricLine],
    *,
    width: int,
    height: int,
    font_name: str,
    font_size: int,
    text_color: str,
    accent_color: str,
    max_line_duration: float,
    show_context: bool,
    subtitle_style: str = "elegant",
    y_percent: float = 50.0,
    letter_spacing: float | None = None,
    alignment: str = "center",
    motion_preset: str = "cinematic",
    section_automation: list[dict[str, object]] | None = None,
    section_time_offset: float = 0.0,
) -> str:
    if not lines:
        raise ValueError("没有可渲染的歌词。")

    if subtitle_style not in SUBTITLE_STYLES:
        raise ValueError(f"未知字幕样式：{subtitle_style}")
    if not 10 <= y_percent <= 90:
        raise ValueError("字幕纵向位置必须在 10 到 90 之间。")
    if alignment not in {"left", "center", "right"}:
        raise ValueError("字幕对齐方式必须是 left、center 或 right。")
    if motion_preset not in MOTION_PRESETS:
        raise ValueError(f"未知歌词动效：{motion_preset}")
    for section in section_automation or []:
        section_motion = str(section.get("motionPreset", motion_preset))
        if section_motion not in MOTION_PRESETS:
            raise ValueError(f"段落中包含未知歌词动效：{section_motion}")

    style = SUBTITLE_STYLES[subtitle_style]
    alignment_code = {"left": 4, "center": 5, "right": 6}[alignment]
    center_x = round(width * {"left": 0.12, "center": 0.5, "right": 0.88}[alignment])
    center_y = round(height * y_percent / 100)
    context_gap = max(78, round(font_size * 1.55))
    context_size = max(24, round(font_size * 0.47))
    outline = max(0, float(style["outline"]) * font_size / 76)
    shadow = max(0, float(style["shadow"]) * font_size / 76)
    spacing = float(style["spacing"]) if letter_spacing is None else letter_spacing
    bold = -1 if style["bold"] else 0
    italic = -1 if style["italic"] else 0
    border_style = 3 if style.get("capsule") else 1
    primary_alpha = 255 if style.get("hollow") else 0
    outline_color = accent_color if style.get("neon") or style.get("hollow") else "#05070D"
    style_tags = r"\blur3.2" if style.get("neon") else ""

    header = f"""[Script Info]
; Generated by lyrics_mv.py
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Current,{font_name},{font_size},{_ass_color(text_color, primary_alpha)},{_ass_color(accent_color)},{_ass_color(outline_color, 18)},{_ass_color('#080A10', 105)},{bold},{italic},0,0,100,100,{spacing},0,{border_style},{outline:.2f},{shadow:.2f},{alignment_code},90,90,40,1
Style: Context,{font_name},{context_size},{_ass_color(accent_color, 135)},{_ass_color(accent_color, 135)},{_ass_color('#05070D', 100)},{_ass_color('#000000', 180)},0,0,0,0,100,100,0.5,0,1,{max(1, outline - 1)},0,5,120,120,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []
    for index, line in enumerate(lines):
        # Single-line mode keeps the outgoing sentence alive for the final
        # 320 ms while the next one enters, producing a true visual handoff.
        end = _line_end(
            lines,
            index,
            max_line_duration,
            handoff_overlap=0.32 if not show_context else -0.02,
        )
        if end <= line.start:
            continue
        start_ass = _ass_timestamp(line.start)
        end_ass = _ass_timestamp(end)
        lyric = _ass_escape(line.text)
        duration_ms = max(1, round((end - line.start) * 1000))
        event_motion = motion_preset
        event_intensity = 0.6
        section_time = line.start - section_time_offset
        for section in section_automation or []:
            start = float(section.get("start", 0.0))
            section_end = float(section.get("end", math.inf))
            if start <= section_time < section_end:
                event_motion = str(section.get("motionPreset", motion_preset))
                event_intensity = float(section.get("motionIntensity", 0.6))
                break
        current_tags = "{" + _motion_tags(
            event_motion,
            x=center_x,
            y=center_y,
            alignment_code=alignment_code,
            duration_ms=duration_ms,
            line_index=index,
            intensity=event_intensity,
        ) + style_tags + "}"
        events.append(
            f"Dialogue: 2,{start_ass},{end_ass},Current,,0,0,0,,{current_tags}{lyric}"
        )

        if show_context and index > 0:
            previous = _ass_escape(lines[index - 1].text)
            tags = rf"{{\an{alignment_code}\pos({center_x},{center_y - context_gap})\fad(180,180)\blur0.2}}"
            events.append(
                f"Dialogue: 1,{start_ass},{end_ass},Context,,0,0,0,,{tags}{previous}"
            )
        if show_context and index + 1 < len(lines):
            upcoming = _ass_escape(lines[index + 1].text)
            tags = rf"{{\an{alignment_code}\pos({center_x},{center_y + context_gap})\fad(180,180)\blur0.2}}"
            events.append(
                f"Dialogue: 1,{start_ass},{end_ass},Context,,0,0,0,,{tags}{upcoming}"
            )

    return header + "\n".join(events) + "\n"


def _ffmpeg_has_filter(ffmpeg: Path, filter_name: str) -> bool:
    result = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode == 0 and re.search(
        rf"\b{re.escape(filter_name)}\s+(?:V->V|\|->V)", result.stdout
    ) is not None


def _find_ffmpeg(explicit: Path | None) -> Path:
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if not candidate.is_file():
            raise FileNotFoundError(f"指定的 FFmpeg 不存在：{candidate}")
        return candidate

    env_binary = os.environ.get("LYRICS_MV_FFMPEG")
    if env_binary:
        candidate = Path(env_binary).expanduser().resolve()
        if candidate.is_file():
            return candidate

    system_binary = shutil.which("ffmpeg")
    system_candidate = Path(system_binary) if system_binary else None
    if system_candidate and _ffmpeg_has_filter(system_candidate, "ass"):
        return system_candidate

    try:
        import imageio_ffmpeg  # type: ignore

        return Path(imageio_ffmpeg.get_ffmpeg_exe())
    except (ImportError, RuntimeError) as exc:
        if system_candidate:
            return system_candidate
        raise RuntimeError(
            "没有找到 FFmpeg。请安装系统 FFmpeg，或运行："
            "python -m pip install -r requirements.txt"
        ) from exc


def _copy_font_files(temp_fonts: Path, font_file: Path | None) -> tuple[str, bool]:
    temp_fonts.mkdir(parents=True, exist_ok=True)
    if font_file:
        source = font_file.expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"字体文件不存在：{source}")
        shutil.copy2(source, temp_fonts / source.name)
        return "", True

    candidates: list[tuple[str, list[Path]]] = []
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    candidates.extend(
        [
            ("Noto Serif SC", [windows_fonts / "NotoSerifSC-VF.ttf"]),
            (
                "Noto Sans SC",
                [
                    windows_fonts / "Noto Sans SC (TrueType).otf",
                    windows_fonts / "Noto Sans SC Bold (TrueType).otf",
                ],
            ),
            ("Microsoft YaHei", [windows_fonts / "msyh.ttc", windows_fonts / "msyhbd.ttc"]),
            ("SimHei", [windows_fonts / "simhei.ttf"]),
            ("SimSun", [windows_fonts / "simsun.ttc"]),
            (
                "Noto Sans CJK SC",
                [
                    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
                    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
                ],
            ),
            ("PingFang SC", [Path("/System/Library/Fonts/PingFang.ttc")]),
        ]
    )

    for family, paths in candidates:
        existing = [path for path in paths if path.is_file()]
        if existing:
            for source in existing:
                shutil.copy2(source, temp_fonts / source.name)
            return family, True
    return "Arial", False


def _probe_ass_support(ffmpeg: Path) -> None:
    if not _ffmpeg_has_filter(ffmpeg, "ass"):
        raise RuntimeError(
            "当前 FFmpeg 没有 libass/ass 字幕滤镜。请换用完整构建，"
            "或安装 requirements.txt 中的 imageio-ffmpeg。"
        )


def _validate_dimensions(width: int, height: int, fps: int) -> None:
    if width < 320 or height < 320 or width % 2 or height % 2:
        raise ValueError("宽高必须是不小于 320 的偶数。")
    if not 1 <= fps <= 60:
        raise ValueError("FPS 必须在 1 到 60 之间。")


def _background_source(
    width: int, height: int, fps: int, colors: list[str], *, gradient_supported: bool
) -> str:
    normalized = [color.strip().lstrip("#") for color in colors]
    for color in normalized:
        _ass_color(color)
    if not gradient_supported:
        return f"color=c=0x{normalized[0]}:s={width}x{height}:r={fps}"
    color_args = ":".join(f"c{i}=0x{color}" for i, color in enumerate(normalized))
    return (
        f"gradients=s={width}x{height}:r={fps}:{color_args}:"
        f"n={len(normalized)}:type=radial:speed=0.0015"
    )


def _image_background_filter(
    *,
    width: int,
    height: int,
    fps: int,
    loop_seconds: float,
    motion_strength: float,
    dim: float,
) -> str:
    """Build a periodic Ken Burns motion whose first and last states match."""
    period_frames = fps * loop_seconds
    zoom_amount = 0.045 * motion_strength
    pan_amount = 0.34 * motion_strength
    phase = f"2*PI*on/{period_frames:.6f}"
    zoom = f"1+{zoom_amount:.6f}*(1-cos({phase}))/2"
    x = f"iw/2-(iw/zoom/2)+(iw-iw/zoom)*{pan_amount:.6f}*sin({phase})"
    y = f"ih/2-(ih/zoom/2)+(ih-ih/zoom)*{pan_amount * 0.72:.6f}*sin({phase}+PI/2)"
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s={width}x{height}:fps={fps},"
        "eq=brightness=-0.035:saturation=0.92,"
        f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{dim:.3f}:t=fill,"
        "vignette=PI/5"
    )


def _video_background_filter(
    *, width: int, height: int, fps: int, dim: float
) -> str:
    """Normalize a loop-ready background clip before subtitle compositing."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},"
        "eq=brightness=-0.025:saturation=0.94,"
        f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{dim:.3f}:t=fill,"
        "vignette=PI/5"
    )


def render(args: argparse.Namespace) -> Path:
    audio = args.audio.expanduser().resolve()
    lrc = args.lrc.expanduser().resolve()
    background_image = (
        args.background_image.expanduser().resolve() if args.background_image else None
    )
    background_video = (
        args.background_video.expanduser().resolve() if args.background_video else None
    )
    output = (
        args.output.expanduser().resolve()
        if args.output
        else audio.with_name(audio.stem + "_lyrics_mv.mp4")
    )

    if not audio.is_file():
        raise FileNotFoundError(f"音频不存在：{audio}")
    if audio.suffix.lower() not in {".mp3", ".wav"}:
        raise ValueError("音频仅支持 .mp3 或 .wav。")
    if not lrc.is_file():
        raise FileNotFoundError(f"LRC 不存在：{lrc}")
    if background_image and not background_image.is_file():
        raise FileNotFoundError(f"背景图片不存在：{background_image}")
    if background_image and background_image.suffix.lower() not in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
    }:
        raise ValueError("背景图片仅支持 PNG、JPG、JPEG、WebP 或 BMP。")
    if background_video and not background_video.is_file():
        raise FileNotFoundError(f"背景视频不存在：{background_video}")
    if background_video and background_video.suffix.lower() not in {
        ".mp4",
        ".mov",
        ".webm",
        ".mkv",
    }:
        raise ValueError("背景视频仅支持 MP4、MOV、WebM 或 MKV。")
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"输出已存在：{output}。如需覆盖，请加 --overwrite。")
    output.parent.mkdir(parents=True, exist_ok=True)
    _validate_dimensions(args.width, args.height, args.fps)
    if args.font_size <= 0:
        raise ValueError("字体大小必须大于 0。")
    if args.max_line_duration <= 0:
        raise ValueError("单句最长显示时间必须大于 0。")
    if not 0 <= args.crf <= 51:
        raise ValueError("CRF 必须在 0 到 51 之间。")
    if args.loop_seconds <= 0:
        raise ValueError("背景循环时长必须大于 0。")
    if not 0 <= args.motion_strength <= 1:
        raise ValueError("背景运动强度必须在 0 到 1 之间。")
    if not 0 <= args.background_dim <= 0.9:
        raise ValueError("背景压暗强度必须在 0 到 0.9 之间。")

    section_automation: list[dict[str, object]] = []
    if args.section_automation:
        parsed_automation = json.loads(args.section_automation)
        if not isinstance(parsed_automation, list) or not all(isinstance(item, dict) for item in parsed_automation):
            raise ValueError("section-automation 必须是 JSON 对象数组。")
        section_automation = parsed_automation

    document = parse_lrc(lrc)
    lrc_offset = 0.0 if args.ignore_lrc_offset else document.lrc_offset_seconds
    effective_offset = args.offset + lrc_offset
    shifted = apply_offset(document.lines, effective_offset)
    ffmpeg = _find_ffmpeg(args.ffmpeg)
    _probe_ass_support(ffmpeg)

    print(f"歌词行数：{len(shifted)}")
    print(f"音频延迟：{args.offset:.3f} 秒")
    if lrc_offset:
        print(f"LRC 内置 offset：{lrc_offset:.3f} 秒")
    print(f"实际歌词偏移：{effective_offset:.3f} 秒")
    print(f"FFmpeg：{ffmpeg}")

    temp_root: Path
    temp_context = None
    if args.keep_temp:
        temp_root = output.with_name(output.stem + "_render_files")
        temp_root.mkdir(parents=True, exist_ok=True)
    else:
        temp_context = tempfile.TemporaryDirectory(prefix="lyrics-mv-")
        temp_root = Path(temp_context.name)

    try:
        fonts_dir = temp_root / "fonts"
        detected_font, found_font = _copy_font_files(fonts_dir, args.font_file)
        font_name = args.font_name or detected_font
        if args.font_file and not args.font_name:
            raise ValueError("使用 --font-file 时还必须提供该字体内部的 --font-name。")
        if not found_font:
            print("警告：未找到中文字体，将回退到 Arial；中文可能显示为方框。", file=sys.stderr)

        ass_text = build_ass(
            shifted,
            width=args.width,
            height=args.height,
            font_name=font_name,
            font_size=args.font_size,
            text_color=args.text_color,
            accent_color=args.accent_color,
            max_line_duration=args.max_line_duration,
            show_context=args.display_mode == "stack" and not args.no_context,
            subtitle_style=args.subtitle_style,
            y_percent=args.subtitle_y,
            letter_spacing=args.letter_spacing,
            alignment=args.subtitle_align,
            motion_preset=args.motion_preset,
            section_automation=section_automation,
            section_time_offset=effective_offset,
        )
        ass_path = temp_root / "captions.ass"
        ass_path.write_text(ass_text, encoding="utf-8-sig")

        manifest = {
            "audio": str(audio),
            "lrc": str(lrc),
            "output": str(output),
            "audio_offset_seconds": args.offset,
            "lrc_offset_seconds": lrc_offset,
            "effective_offset_seconds": effective_offset,
            "resolution": {"width": args.width, "height": args.height, "fps": args.fps},
            "font": font_name,
            "subtitle_style": args.subtitle_style,
            "subtitle_motion_preset": args.motion_preset,
            "subtitle_display_mode": args.display_mode,
            "subtitle_section_automation": section_automation,
            "subtitle_y_percent": args.subtitle_y,
            "subtitle_alignment": args.subtitle_align,
            "subtitle_letter_spacing": args.letter_spacing,
            "background_image": str(background_image) if background_image else None,
            "background_video": str(background_video) if background_video else None,
            "background_loop_seconds": args.loop_seconds,
            "background_motion_strength": args.motion_strength,
            "background_dim": args.background_dim,
            "metadata": document.metadata,
            "lyrics": [asdict(line) for line in shifted],
        }
        (temp_root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        command = [
            str(ffmpeg),
            "-hide_banner",
            "-y" if args.overwrite else "-n",
        ]
        if background_image:
            command.extend(
                ["-loop", "1", "-framerate", str(args.fps), "-i", str(background_image)]
            )
            visual_filter = _image_background_filter(
                width=args.width,
                height=args.height,
                fps=args.fps,
                loop_seconds=args.loop_seconds,
                motion_strength=args.motion_strength,
                dim=args.background_dim,
            )
        elif background_video:
            command.extend(["-stream_loop", "-1", "-i", str(background_video)])
            visual_filter = _video_background_filter(
                width=args.width,
                height=args.height,
                fps=args.fps,
                dim=args.background_dim,
            )
        else:
            background = _background_source(
                args.width,
                args.height,
                args.fps,
                args.background_colors,
                gradient_supported=_ffmpeg_has_filter(ffmpeg, "gradients"),
            )
            command.extend(["-f", "lavfi", "-i", background])
            visual_filter = "vignette=PI/5,noise=alls=1.2:allf=t"
        filter_chain = (
            visual_filter
            + ",ass=captions.ass:fontsdir=fonts,format=yuv420p"
        )
        command.extend(
            [
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            filter_chain,
            "-c:v",
            "libx264",
            "-preset",
            args.preset,
            "-crf",
            str(args.crf),
            "-c:a",
            "aac",
            "-b:a",
            args.audio_bitrate,
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
            ]
        )
        if args.dry_run:
            print("\nDry run；未执行渲染。命令如下：")
            print(subprocess.list2cmdline(command))
            print(f"ASS：{ass_path}")
            return output

        print(f"开始渲染：{output}")
        completed = subprocess.run(command, cwd=temp_root, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"FFmpeg 渲染失败，退出码：{completed.returncode}")
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("FFmpeg 未产生有效输出文件。")
        print(f"渲染完成：{output}")
        return output
    finally:
        if temp_context is not None:
            temp_context.cleanup()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="将 MP3/WAV 和无音频延迟的 LRC 渲染为纯歌词 MV。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("audio", type=Path, help="输入音频（.mp3 或 .wav）")
    parser.add_argument("lrc", type=Path, help="与歌曲本体对齐、未包含音频前置延迟的 .lrc")
    parser.add_argument(
        "--offset",
        type=float,
        required=True,
        metavar="SECONDS",
        help="歌曲在输入音频中开始的秒数 x；所有歌词时间都会加 x",
    )
    parser.add_argument("-o", "--output", type=Path, help="输出 MP4 路径")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已有输出")
    parser.add_argument("--width", type=int, default=1920, help="视频宽度")
    parser.add_argument("--height", type=int, default=1080, help="视频高度")
    parser.add_argument("--fps", type=int, default=30, help="视频帧率")
    parser.add_argument("--font-size", type=int, default=76, help="当前歌词字号")
    parser.add_argument("--font-name", help="ASS 字体内部名称，例如 Microsoft YaHei")
    parser.add_argument("--font-file", type=Path, help="自定义 TTF/TTC/OTF 字体文件")
    parser.add_argument("--text-color", default="#F7F7FA", help="当前歌词颜色")
    parser.add_argument("--accent-color", default="#8AD8FF", help="字幕次要颜色")
    parser.add_argument(
        "--subtitle-style",
        choices=sorted(SUBTITLE_STYLES),
        default="elegant",
        help="字幕视觉样式",
    )
    parser.add_argument(
        "--motion-preset",
        choices=MOTION_PRESETS,
        default="cinematic",
        help="逐句歌词的进入、停留和离场动效",
    )
    parser.add_argument(
        "--display-mode",
        choices=["single", "stack"],
        default="single",
        help="single 仅显示当前句，stack 同时显示淡化的前后句",
    )
    parser.add_argument(
        "--section-automation",
        help="情感导演生成的 JSON 数组；按歌曲段落切换动效与强度",
    )
    parser.add_argument(
        "--subtitle-y",
        type=float,
        default=50.0,
        help="字幕中心的纵向百分比位置，范围 10 到 90",
    )
    parser.add_argument(
        "--subtitle-align",
        choices=["left", "center", "right"],
        default="center",
        help="字幕水平对齐",
    )
    parser.add_argument(
        "--letter-spacing",
        type=float,
        help="ASS 字符间距；不传时使用所选字幕样式的默认值",
    )
    background_group = parser.add_mutually_exclusive_group()
    background_group.add_argument(
        "--background-image",
        type=Path,
        help="AI 生成或人工选择的背景图；提供后将替代自动渐变背景",
    )
    background_group.add_argument(
        "--background-video",
        type=Path,
        help="可循环的背景视频；会循环到歌曲结束并在其上叠加字幕",
    )
    parser.add_argument(
        "--loop-seconds",
        type=float,
        default=12.0,
        help="静态背景图运动循环的周期秒数",
    )
    parser.add_argument(
        "--motion-strength",
        type=float,
        default=0.6,
        help="背景缩放与漂移强度，范围 0 到 1",
    )
    parser.add_argument(
        "--background-dim",
        type=float,
        default=0.24,
        help="背景黑色遮罩强度，范围 0 到 0.9",
    )
    parser.add_argument(
        "--background-colors",
        nargs=3,
        default=["#080B16", "#1A1233", "#06212B"],
        metavar=("COLOR1", "COLOR2", "COLOR3"),
        help="动态渐变背景的三个颜色",
    )
    parser.add_argument(
        "--max-line-duration",
        type=float,
        default=8.0,
        help="下一句很晚时，单句歌词最多保留的秒数",
    )
    parser.add_argument("--no-context", action="store_true", help="兼容旧配置：强制不显示淡化的前后歌词")
    parser.add_argument("--ignore-lrc-offset", action="store_true", help="忽略 LRC 内的 [offset:毫秒]")
    parser.add_argument("--crf", type=int, default=18, help="H.264 画质；越小越清晰、文件越大")
    parser.add_argument(
        "--preset",
        choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"],
        default="medium",
        help="H.264 编码速度预设",
    )
    parser.add_argument("--audio-bitrate", default="320k", help="AAC 音频码率")
    parser.add_argument("--ffmpeg", type=Path, help="显式指定 FFmpeg 可执行文件")
    parser.add_argument("--keep-temp", action="store_true", help="保留 ASS 和 manifest 调试文件")
    parser.add_argument("--dry-run", action="store_true", help="只生成临时文件并打印命令")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        render(args)
        return 0
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
