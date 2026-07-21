#!/usr/bin/env python3
"""Analyze a song and turn its musical shape into an AutoMV visual direction.

The analysis is deliberately interpretable. It estimates acoustic energy,
brightness, pulse, tempo and section contrast; it does not claim to understand
lyrics or identify a song's true emotional meaning without an LRC/LLM pass.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


MOTION_PRESETS = {"cinematic", "float", "punch", "handwritten", "neon", "minimal"}


@dataclass(frozen=True)
class AudioFeatures:
    duration_seconds: float
    tempo_bpm: float
    tempo_confidence: float
    rms_db: float
    dynamic_range_db: float
    spectral_centroid_hz: float
    zero_crossing_rate: float
    onset_activity: float
    arousal: float
    brightness: float
    rhythmicity: float


def find_ffmpeg(explicit: Path | None = None) -> Path:
    if explicit:
        value = explicit.expanduser().resolve()
        if not value.is_file():
            raise FileNotFoundError(f"FFmpeg 不存在：{value}")
        return value
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("没有找到 FFmpeg；请安装 FFmpeg 或使用 --ffmpeg 指定路径。")
    return Path(found)


def decode_audio(path: Path, ffmpeg: Path, sample_rate: int = 22_050) -> np.ndarray:
    command = [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1",
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"FFmpeg 无法解码 {path.name}：{detail.strip()}")
    samples = np.frombuffer(result.stdout, dtype="<f4").astype(np.float32, copy=True)
    if samples.size < sample_rate:
        raise ValueError(f"音频过短，无法分析：{path}")
    return samples


def _frames(samples: np.ndarray, frame_size: int, hop: int) -> np.ndarray:
    if samples.size < frame_size:
        samples = np.pad(samples, (0, frame_size - samples.size))
    count = 1 + (samples.size - frame_size) // hop
    shape = (count, frame_size)
    strides = (samples.strides[0] * hop, samples.strides[0])
    return np.lib.stride_tricks.as_strided(samples, shape=shape, strides=strides)


def _estimate_tempo(onset: np.ndarray, frame_rate: float) -> tuple[float, float]:
    centered = onset.astype(np.float64) - float(np.mean(onset))
    if centered.size < 16 or float(np.std(centered)) < 1e-8:
        return 0.0, 0.0
    fft_size = 1 << (2 * centered.size - 1).bit_length()
    spectrum = np.fft.rfft(centered, fft_size)
    autocorr = np.fft.irfft(spectrum * np.conj(spectrum), fft_size)[: centered.size]
    autocorr /= max(float(autocorr[0]), 1e-9)
    bpms = np.arange(55.0, 191.0, 0.5)
    lags = np.rint(60.0 * frame_rate / bpms).astype(int)
    valid = (lags > 0) & (lags < autocorr.size)
    if not np.any(valid):
        return 0.0, 0.0
    valid_bpms = bpms[valid]
    scores = autocorr[lags[valid]]
    preference = np.exp(-0.5 * ((valid_bpms - 105.0) / 55.0) ** 2)
    index = int(np.argmax(scores * (0.82 + 0.18 * preference)))
    return float(valid_bpms[index]), float(np.clip(scores[index], 0.0, 1.0))


def analyze_samples(samples: np.ndarray, sample_rate: int = 22_050) -> tuple[AudioFeatures, list[dict[str, Any]]]:
    samples = np.asarray(samples, dtype=np.float32)
    peak = float(np.max(np.abs(samples)))
    if peak > 1.5:
        samples = samples / peak

    frame_size = 2048
    hop = 1024
    framed = _frames(samples, frame_size, hop)
    window = np.hanning(frame_size).astype(np.float32)
    windowed = framed * window
    rms = np.sqrt(np.mean(framed.astype(np.float64) ** 2, axis=1) + 1e-12)
    rms_db_frames = 20.0 * np.log10(rms + 1e-12)

    magnitude = np.abs(np.fft.rfft(windowed, axis=1)).astype(np.float32)
    frequencies = np.fft.rfftfreq(frame_size, 1.0 / sample_rate).astype(np.float32)
    magnitude_sum = np.sum(magnitude, axis=1) + 1e-9
    centroid = np.sum(magnitude * frequencies, axis=1) / magnitude_sum
    normalized = magnitude / magnitude_sum[:, None]
    flux = np.zeros(len(normalized), dtype=np.float32)
    if len(normalized) > 1:
        flux[1:] = np.sqrt(np.sum(np.maximum(normalized[1:] - normalized[:-1], 0.0) ** 2, axis=1))

    signs = framed >= 0
    zcr = np.mean(signs[:, 1:] != signs[:, :-1], axis=1)
    frame_rate = sample_rate / hop
    tempo, tempo_confidence = _estimate_tempo(flux, frame_rate)

    active_floor = max(-72.0, float(np.percentile(rms_db_frames, 90)) - 42.0)
    active = rms_db_frames >= active_floor
    active_db = rms_db_frames[active] if np.any(active) else rms_db_frames
    rms_db = float(np.percentile(active_db, 65))
    dynamic_range = float(np.clip(np.percentile(active_db, 90) - np.percentile(active_db, 10), 0.0, 36.0))
    spectral_centroid = float(np.median(centroid[active])) if np.any(active) else float(np.median(centroid))
    zero_crossing = float(np.median(zcr[active])) if np.any(active) else float(np.median(zcr))
    flux_scale = float(np.percentile(flux, 90)) + 1e-9
    onset_threshold = float(np.median(flux) + 1.5 * np.std(flux))
    onset_density = float(np.mean(flux > onset_threshold))
    onset_activity = float(np.clip(0.35 * np.mean(flux) / flux_scale + 0.65 * onset_density * 5.0, 0.0, 1.0))

    if tempo > 160 and tempo_confidence < 0.45:
        tempo /= 2.0
    elif 0 < tempo < 70:
        tempo *= 2.0

    loudness_energy = float(np.clip((rms_db + 32.0) / 22.0, 0.0, 1.0))
    tempo_energy = float(np.clip((tempo - 60.0) / 100.0, 0.0, 1.0)) if tempo else 0.35
    brightness = float(np.clip((spectral_centroid - 700.0) / 3600.0, 0.0, 1.0))
    rhythmicity = float(np.clip(0.62 * tempo_confidence + 0.38 * onset_activity, 0.0, 1.0))
    arousal = float(np.clip(0.48 * loudness_energy + 0.28 * tempo_energy + 0.24 * rhythmicity, 0.0, 1.0))

    duration = samples.size / sample_rate
    sections = _energy_sections(rms_db_frames, hop / sample_rate, duration)
    features = AudioFeatures(
        duration_seconds=round(duration, 3),
        tempo_bpm=round(tempo, 1),
        tempo_confidence=round(tempo_confidence, 3),
        rms_db=round(rms_db, 2),
        dynamic_range_db=round(dynamic_range, 2),
        spectral_centroid_hz=round(spectral_centroid, 1),
        zero_crossing_rate=round(zero_crossing, 4),
        onset_activity=round(onset_activity, 3),
        arousal=round(arousal, 3),
        brightness=round(brightness, 3),
        rhythmicity=round(rhythmicity, 3),
    )
    return features, sections


def _energy_sections(rms_db: np.ndarray, frame_seconds: float, duration: float) -> list[dict[str, Any]]:
    bin_seconds = 2.0
    frames_per_bin = max(1, round(bin_seconds / frame_seconds))
    values = [float(np.mean(rms_db[i : i + frames_per_bin])) for i in range(0, len(rms_db), frames_per_bin)]
    curve = np.asarray(values, dtype=np.float64)
    if curve.size == 0:
        return []
    kernel = np.ones(5) / 5
    smooth = np.convolve(np.pad(curve, (2, 2), mode="edge"), kernel, mode="valid")
    low, high = np.percentile(smooth, [10, 90])
    relative = np.clip((smooth - low) / max(high - low, 1e-6), 0.0, 1.0)
    change = np.abs(np.diff(relative, prepend=relative[0]))
    threshold = max(0.12, float(np.percentile(change, 78)))
    candidates = list(np.argsort(change)[::-1])
    boundaries = [0]
    min_gap_bins = max(4, round(10 / bin_seconds))
    for index in candidates:
        if change[index] < threshold or len(boundaries) >= 7:
            break
        if all(abs(index - existing) >= min_gap_bins for existing in boundaries):
            boundaries.append(int(index))
    boundaries = sorted(set(boundaries + [len(relative)]))

    sections: list[dict[str, Any]] = []
    for section_index, (start_bin, end_bin) in enumerate(zip(boundaries, boundaries[1:])):
        start = start_bin * bin_seconds
        end = min(duration, end_bin * bin_seconds)
        if end - start < 2:
            continue
        energy = float(np.mean(relative[start_bin:end_bin]))
        if section_index == 0 and start < 0.5:
            role = "intro_or_opening"
        elif end >= duration - 1.0:
            role = "outro_or_finale"
        elif energy >= 0.72:
            role = "peak_or_chorus"
        elif energy <= 0.3:
            role = "breakdown_or_quiet_verse"
        else:
            slope = float(relative[end_bin - 1] - relative[start_bin])
            role = "build" if slope > 0.18 else "verse_or_transition"
        sections.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "relativeEnergy": round(energy, 3),
            "roleGuess": role,
        })
    return sections


def _emotion_label(features: AudioFeatures) -> tuple[str, list[str], float]:
    arousal = features.arousal
    bright = features.brightness
    if arousal >= 0.66 and bright >= 0.48:
        return "明亮高能", ["兴奋", "推进", "外放"], 0.7
    if arousal >= 0.66:
        return "深色高能", ["强烈", "紧张", "夜色"], 0.66
    if arousal <= 0.38 and bright >= 0.5:
        return "轻盈低能", ["空气感", "希望", "克制"], 0.6
    if arousal <= 0.38:
        return "私密低能", ["内省", "温柔", "忧郁倾向"], 0.64
    if bright >= 0.52:
        return "清澈中能", ["流动", "开阔", "轻快倾向"], 0.58
    return "温暖中能", ["叙事", "回忆", "渐进"], 0.58


def recommend_visual(features: AudioFeatures, sections: list[dict[str, Any]]) -> dict[str, Any]:
    label, tags, confidence = _emotion_label(features)
    if label == "明亮高能":
        base = ("collage", "poster", "punch", ["#102F70", "#EF493F", "#76C8EA"], "#FFFAF0", "#FF5548", 0.26, 0.74, 9.0)
    elif label == "深色高能":
        base = ("neon", "neon", "neon", ["#10071F", "#562489", "#D43FEA"], "#FFF7FF", "#E85CFF", 0.42, 0.68, 10.0)
    elif label == "轻盈低能":
        base = ("diary", "ink", "float", ["#123B43", "#A98768", "#E9DFCA"], "#FFFDF7", "#E5C39D", 0.34, 0.3, 16.0)
    elif label == "私密低能":
        base = ("film", "elegant", "cinematic", ["#0D1524", "#665442", "#C9A47D"], "#FFF9EF", "#D9AD7C", 0.46, 0.24, 17.0)
    elif label == "清澈中能":
        base = ("diary", "ink", "float", ["#0A3540", "#8E755E", "#D8D4C8"], "#FFFDF7", "#DAB78F", 0.36, 0.48, 13.0)
    else:
        base = ("film", "elegant", "cinematic", ["#101827", "#81684F", "#D8B68F"], "#FFF9EF", "#D9AD7C", 0.42, 0.4, 14.0)

    direction, style, motion, colors, text, accent, dim, bg_motion, loop = base
    section_automation = []
    for section in sections:
        energy = float(section["relativeEnergy"])
        if features.arousal < 0.38:
            if energy < 0.24:
                section_motion = "minimal"
            elif energy < 0.68:
                section_motion = "handwritten" if direction == "diary" else "cinematic"
            else:
                section_motion = "float" if direction == "diary" else "cinematic"
        elif features.arousal < 0.66:
            if energy < 0.24:
                section_motion = "minimal"
            elif energy < 0.66:
                section_motion = "cinematic"
            else:
                section_motion = "float"
        else:
            if energy < 0.3:
                section_motion = "cinematic"
            elif energy < 0.7:
                section_motion = "float"
            else:
                section_motion = "neon" if direction == "neon" else "punch"
        section_automation.append({
            "start": section["start"],
            "end": section["end"],
            "motionPreset": section_motion,
            "motionIntensity": round(0.22 + energy * 0.72, 3),
            "backgroundMotionStrength": round(min(0.9, bg_motion * (0.65 + energy * 0.7)), 3),
            "accentAmount": round(0.08 + energy * 0.24, 3),
        })

    return {
        "emotion": {
            "acousticCharacter": label,
            "tags": tags,
            "confidence": confidence,
            "limitations": "仅由声学特征推断；拿到 LRC 后必须结合歌词语义和人工听感复核，不能把明亮音色直接等同于正面情绪。",
        },
        "visualDirection": direction,
        "background": {
            "colors": colors,
            "dim": dim,
            "motionStrength": bg_motion,
            "loopSeconds": loop,
        },
        "subtitles": {
            "style": style,
            "motionPreset": motion,
            "displayMode": "single",
            "fontSize": 64 if features.arousal >= 0.66 else 58,
            "letterSpacingEm": 0.02 if features.arousal >= 0.66 else 0.08,
            "yPercent": 52,
            "align": "center",
            "textColor": text,
            "accentColor": accent,
        },
        "sectionAutomation": section_automation,
    }


def _score_similarity(value: Any, target: Any, compatible: set[Any] | None = None) -> float:
    if value == target:
        return 100.0
    if compatible and value in compatible:
        return 78.0
    return 48.0


def evaluate_project(recommendation: dict[str, Any], project: dict[str, Any] | None) -> dict[str, Any]:
    project = project or {
        "visualDirection": "film",
        "background": {"dim": 0.42, "motionStrength": 0.4, "loopSeconds": 14},
        "subtitles": {
            "style": "elegant", "motionPreset": "cinematic", "displayMode": "single",
            "fontSize": 58, "yPercent": 52, "align": "center",
        },
    }
    subtitles = project.get("subtitles", {}) if isinstance(project.get("subtitles"), dict) else {}
    background = project.get("background", {}) if isinstance(project.get("background"), dict) else {}
    target_subtitles = recommendation["subtitles"]
    target_background = recommendation["background"]
    sections = project.get("sectionAutomation") or subtitles.get("sectionAutomation")

    direction_groups = {
        "film": {"diary", "mono"}, "diary": {"film", "chalk"}, "collage": {"neon"},
        "neon": {"collage", "mono"}, "chalk": {"diary", "film"}, "mono": {"film", "neon"},
    }
    style_groups = {
        "elegant": {"editorial", "ink"}, "ink": {"elegant", "editorial"},
        "poster": {"modern", "outline"}, "neon": {"modern", "outline"},
    }
    motion_groups = {
        "cinematic": {"minimal", "handwritten"}, "float": {"cinematic", "handwritten"},
        "punch": {"float", "neon"}, "neon": {"punch", "float"}, "minimal": {"cinematic"},
        "handwritten": {"cinematic", "float"},
    }
    direction_score = _score_similarity(project.get("visualDirection"), recommendation["visualDirection"], direction_groups.get(recommendation["visualDirection"]))
    acoustic_confidence = float(recommendation.get("emotion", {}).get("confidence", 0.5))
    direction_score *= 0.75 + 0.25 * acoustic_confidence
    typography_score = _score_similarity(subtitles.get("style"), target_subtitles["style"], style_groups.get(target_subtitles["style"]))
    motion_score = _score_similarity(subtitles.get("motionPreset"), target_subtitles["motionPreset"], motion_groups.get(target_subtitles["motionPreset"]))
    if sections:
        motion_score = min(100.0, motion_score + 10.0)

    def closeness(value: Any, target: float, tolerance: float) -> float:
        try:
            return max(35.0, 100.0 - abs(float(value) - target) / tolerance * 30.0)
        except (TypeError, ValueError):
            return 35.0

    background_score = round((
        closeness(background.get("dim"), target_background["dim"], 0.2)
        + closeness(background.get("motionStrength"), target_background["motionStrength"], 0.35)
        + closeness(background.get("loopSeconds"), target_background["loopSeconds"], 7.0)
    ) / 3, 1)

    readability = 94.0
    font_size = float(subtitles.get("fontSize", 58))
    y_percent = float(subtitles.get("yPercent", 52))
    if font_size < 42 or font_size > 78:
        readability -= 18
    if not 34 <= y_percent <= 68:
        readability -= 14
    if subtitles.get("displayMode", "single") != "single":
        readability -= 10
    if subtitles.get("align", "center") not in {"left", "center", "right"}:
        readability -= 10

    continuity = 92.0 if subtitles.get("motionPreset") in MOTION_PRESETS else 48.0
    if subtitles.get("displayMode", "single") != "single":
        continuity -= 8
    structural = 92.0 if sections else 46.0
    semantic_evidence = 90.0 if project.get("lyricEmotionAnalysis") else 35.0

    rows = [
        ("情感方向匹配", direction_score, "整体视觉世界是否符合声学情绪"),
        ("字体气质", typography_score, "字形重量与歌曲能量是否协调"),
        ("运动能量", motion_score, "歌词运动速度、幅度与节奏是否匹配"),
        ("背景克制度", background_score, "背景亮度、运动和循环速度是否服务歌词"),
        ("歌词可读性", readability, "字号、位置、显示密度的设计级检查"),
        ("句间连续性", continuity, "是否逐句交接且使用连续运动语法"),
        ("段落起伏", structural, "主歌、副歌、间奏是否有能量层级变化"),
        ("歌词语义证据", semantic_evidence, "是否已用真实 LRC 校正声学情绪推断"),
    ]
    weights = [0.18, 0.1, 0.16, 0.12, 0.13, 0.09, 0.12, 0.1]
    overall = round(sum(score * weight for (_, score, _), weight in zip(rows, weights)), 1)
    return {
        "overallScore": overall,
        "dimensions": [
            {"name": name, "score": round(score, 1), "basis": basis}
            for name, score, basis in rows
        ],
        "strongest": max(rows, key=lambda item: item[1])[0],
        "weakest": min(rows, key=lambda item: item[1])[0],
        "limitations": [
            "这是设计配置与声学特征的一致性评分，不是对最终像素画面的主观审美真值。",
            "背景图实际对比度、歌词语义和逐字演唱法要在有 LRC 与样片后继续复核。",
        ],
    }


def build_profile(path: Path, samples: np.ndarray, sample_rate: int, offset: float, project: dict[str, Any] | None) -> dict[str, Any]:
    start_sample = max(0, round(offset * sample_rate))
    if start_sample >= samples.size - sample_rate:
        raise ValueError("offset 超过或过于接近音频结尾。")
    features, sections = analyze_samples(samples[start_sample:], sample_rate)
    recommendation = recommend_visual(features, sections)
    return {
        "version": 1,
        "source": {"audio": str(path), "offsetSeconds": offset, "sampleRate": sample_rate},
        "features": features.__dict__,
        "sections": sections,
        "recommendation": recommendation,
        "evaluation": evaluate_project(recommendation, project),
    }


def report_markdown(profiles: list[dict[str, Any]]) -> str:
    lines = [
        "# AutoMV 情感导演与自然度评估", "",
        "评分表示当前默认/项目配置与音频声学特征的匹配程度；它不能替代歌词语义和人工审片。", "",
        "| 歌曲 | BPM | 声学性格 | 推荐方向 | 推荐运动 | 当前评分 | 最弱维度 |",
        "|---|---:|---|---|---|---:|---|",
    ]
    for profile in profiles:
        name = Path(profile["source"]["audio"]).name
        features = profile["features"]
        recommendation = profile["recommendation"]
        evaluation = profile["evaluation"]
        lines.append(
            f"| {name} | {features['tempo_bpm']:.1f} | {recommendation['emotion']['acousticCharacter']} | "
            f"{recommendation['visualDirection']} | {recommendation['subtitles']['motionPreset']} | "
            f"{evaluation['overallScore']:.1f} | {evaluation['weakest']} |"
        )
    lines.extend([
        "", "## 使用原则", "",
        "- 先让音频决定运动能量和段落起伏，再让歌词语义修正色彩与具体意象。",
        "- 全曲只保留一套视觉世界；段落变化主要调整运动强度、强调色比例和背景速度。",
        "- 正式制作前先审查 20–30 秒主歌与副歌样片，防止自动评分掩盖真实观感问题。",
    ])
    return "\n".join(lines) + "\n"


def _safe_name(path: Path) -> str:
    value = re.sub(r"[^\w\-]+", "_", path.stem, flags=re.UNICODE).strip("_")
    return value or "song"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="分析歌曲情感与段落起伏，并生成 AutoMV 视觉导演配置。")
    parser.add_argument("input", nargs="?", type=Path, default=Path(r"D:\Downloads\songs"), help="单个 MP3/WAV 或歌曲目录")
    parser.add_argument("--output-dir", type=Path, default=Path("benchmark/emotion"))
    parser.add_argument("--offset", type=float, default=0.0, help="歌曲在输入音频中的已知开始秒数")
    parser.add_argument("--project", type=Path, help="可选：评价现有 automv-project.json")
    parser.add_argument("--sample-rate", type=int, default=22_050)
    parser.add_argument("--ffmpeg", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        input_path = args.input.expanduser().resolve()
        output_dir = args.output_dir.expanduser().resolve()
        if args.offset < 0:
            raise ValueError("offset 不能小于 0。")
        if args.sample_rate < 8_000:
            raise ValueError("sample-rate 不能小于 8000。")
        if input_path.is_dir():
            files = sorted(
                (path for path in input_path.rglob("*") if path.suffix.lower() in {".mp3", ".wav"}),
                key=lambda item: item.name.lower(),
            )
        elif input_path.is_file() and input_path.suffix.lower() in {".mp3", ".wav"}:
            files = [input_path]
        else:
            raise FileNotFoundError(f"没有找到有效的 MP3/WAV 输入：{input_path}")
        if not files:
            raise ValueError("输入目录中没有 MP3/WAV。")

        project = None
        if args.project:
            project = json.loads(args.project.expanduser().resolve().read_text(encoding="utf-8-sig"))
        ffmpeg = find_ffmpeg(args.ffmpeg)
        output_dir.mkdir(parents=True, exist_ok=True)
        profiles = []
        for index, path in enumerate(files, start=1):
            print(f"[{index}/{len(files)}] 分析 {path.name}")
            samples = decode_audio(path, ffmpeg, args.sample_rate)
            profile = build_profile(path, samples, args.sample_rate, args.offset, project)
            profiles.append(profile)
            destination = output_dir / f"{index:02d}_{_safe_name(path)}.director.json"
            destination.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  {profile['recommendation']['emotion']['acousticCharacter']} / {profile['evaluation']['overallScore']:.1f} 分 -> {destination}")
        report = output_dir / "REPORT.md"
        report.write_text(report_markdown(profiles), encoding="utf-8")
        print(f"汇总报告：{report}")
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
