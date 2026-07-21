#!/usr/bin/env python3
"""Render an AutoMV Studio JSON export with the authoritative FFmpeg pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import lyrics_mv


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"项目配置中的 {name} 必须是对象。")
    return value


def _asset_path(base: Path, value: Any, name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"项目配置缺少 {name} 文件名。")
    candidate = Path(value)
    return candidate if candidate.is_absolute() else base / candidate


def project_to_argv(
    project_path: Path,
    *,
    output: Path | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
    keep_temp: bool = False,
) -> list[str]:
    project_path = project_path.expanduser().resolve()
    data = json.loads(project_path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("仅支持 version=1 的 AutoMV 项目配置。")

    base = project_path.parent
    audio = _object(data.get("audio"), "audio")
    lyrics = _object(data.get("lyrics"), "lyrics")
    canvas = _object(data.get("canvas"), "canvas")
    background = _object(data.get("background"), "background")
    subtitles = _object(data.get("subtitles"), "subtitles")
    render = _object(data.get("render"), "render")
    subtitle_font_size = int(subtitles.get("fontSize", 76))
    letter_spacing = subtitles.get("letterSpacing")
    if letter_spacing is None:
        letter_spacing = float(subtitles.get("letterSpacingEm", 0.016)) * subtitle_font_size
    display_mode = subtitles.get("displayMode")
    if display_mode is None:
        display_mode = "stack" if subtitles.get("showContext") is True else "single"
    section_automation = data.get("sectionAutomation", subtitles.get("sectionAutomation", []))
    if not isinstance(section_automation, list):
        raise ValueError("sectionAutomation 必须是数组。")

    audio_path = _asset_path(base, audio.get("file"), "audio.file")
    lrc_path = _asset_path(base, lyrics.get("file"), "lyrics.file")
    argv = [
        str(audio_path),
        str(lrc_path),
        "--offset",
        str(float(audio.get("offsetSeconds", 0))),
        "--width",
        str(int(canvas.get("width", 1920))),
        "--height",
        str(int(canvas.get("height", 1080))),
        "--fps",
        str(int(canvas.get("fps", 30))),
        "--background-dim",
        str(float(background.get("dim", 0.24))),
        "--motion-strength",
        str(float(background.get("motionStrength", 0.6))),
        "--loop-seconds",
        str(float(background.get("loopSeconds", 12))),
        "--subtitle-style",
        str(subtitles.get("style", "elegant")),
        "--motion-preset",
        str(subtitles.get("motionPreset", "cinematic")),
        "--display-mode",
        str(display_mode),
        "--font-size",
        str(subtitle_font_size),
        "--letter-spacing",
        str(float(letter_spacing)),
        "--subtitle-y",
        str(float(subtitles.get("yPercent", 50))),
        "--subtitle-align",
        str(subtitles.get("align", "center")),
        "--text-color",
        str(subtitles.get("textColor", "#F7F7FA")),
        "--accent-color",
        str(subtitles.get("accentColor", "#8AD8FF")),
        "--crf",
        str(int(render.get("crf", 18))),
        "--preset",
        str(render.get("preset", "medium")),
        "--audio-bitrate",
        str(render.get("audioBitrate", "320k")),
    ]
    if section_automation:
        argv.extend(["--section-automation", json.dumps(section_automation, ensure_ascii=False, separators=(",", ":"))])

    background_kind = background.get("kind", "gradient")
    if background_kind in {"image", "video"}:
        background_path = _asset_path(base, background.get("file"), "background.file")
        argv.extend(
            ["--background-image" if background_kind == "image" else "--background-video", str(background_path)]
        )
    elif background_kind != "gradient":
        raise ValueError("background.kind 必须是 gradient、image 或 video。")

    if output:
        argv.extend(["--output", str(output.expanduser().resolve())])
    if overwrite:
        argv.append("--overwrite")
    if dry_run:
        argv.append("--dry-run")
    if keep_temp:
        argv.append("--keep-temp")
    return argv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="渲染 AutoMV Studio 导出的项目 JSON。")
    parser.add_argument("project", type=Path, help="automv-project.json 路径")
    parser.add_argument("-o", "--output", type=Path, help="覆盖配置推导出的输出路径")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已有输出")
    parser.add_argument("--dry-run", action="store_true", help="生成 ASS 与命令但不执行 FFmpeg")
    parser.add_argument("--keep-temp", action="store_true", help="保留 ASS 和 manifest")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        render_argv = project_to_argv(
            args.project,
            output=args.output,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            keep_temp=args.keep_temp,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}")
        return 1
    return lyrics_mv.main(render_argv)


if __name__ == "__main__":
    raise SystemExit(main())
