#!/usr/bin/env python3
"""Benchmark the connected LLM on lyric-MV planning before LRC files exist."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from mv_plan import call_compatible_llm, extract_json


SYSTEM_PROMPT = """你是一名严谨的纯歌词 MV 视觉导演。
你必须严格区分已知证据和推测。当前没有歌词文本，也不能实际听到音频，因此不得编造具体歌词、故事、人物或歌曲身份。
你的任务是在承认信息不足的前提下，根据文件名和技术元数据给出优雅、克制、适合居中歌词的背景方向。
只输出严格 JSON，不要输出 Markdown。"""


def find_ffprobe(explicit: Path | None) -> Path:
    if explicit:
        value = explicit.expanduser().resolve()
        if not value.is_file():
            raise FileNotFoundError(f"ffprobe 不存在：{value}")
        return value
    found = shutil.which("ffprobe")
    if found:
        return Path(found)
    raise RuntimeError("没有找到 ffprobe，请安装完整 FFmpeg 或使用 --ffprobe。")


def probe_audio(path: Path, ffprobe: Path) -> dict[str, Any]:
    command = [
        str(ffprobe),
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels,bits_per_sample",
        "-show_entries",
        "format=duration,bit_rate:format_tags=title,artist",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 读取失败：{path.name}\n{result.stderr}")
    data = json.loads(result.stdout)
    stream = data.get("streams", [{}])[0]
    format_info = data.get("format", {})
    tags = format_info.get("tags", {})
    return {
        "file_name": path.name,
        "duration_seconds": round(float(format_info.get("duration", 0)), 3),
        "codec": stream.get("codec_name"),
        "sample_rate": int(stream.get("sample_rate", 0)),
        "channels": stream.get("channels"),
        "bits_per_sample": stream.get("bits_per_sample"),
        "embedded_title": tags.get("title"),
        "embedded_artist": tags.get("artist"),
        "lyrics_available": False,
    }


def build_benchmark_prompt(info: dict[str, Any], candidate_count: int) -> str:
    evidence = json.dumps(info, ensure_ascii=False, indent=2)
    return f"""请根据下面唯一可用的证据，为纯歌词 MV 提供初步视觉方案：

{evidence}

这是一次模型能力测试。要求：
1. 明确说明没有歌词、无法确认歌曲语义；文件名只能作为弱线索，不能当作事实。
2. 不得声称知道具体歌词、歌手身份、情节或歌曲情绪。
3. 给出 {candidate_count} 个风格彼此不同、但都适合后续加入居中歌词的背景候选。
4. 每个英文 image prompt 必须明确包含：中央低细节负空间、视觉重点在边缘或远景、无文字、无 logo、无水印、16:9 构图、适合缓慢循环缩放和漂移。
5. image_prompt_en 和 negative_prompt_en 必须为英文。
6. motion_strength 范围 0 到 1，background_dim 范围 0 到 0.9，loop_seconds 范围 8 到 18。

只输出以下结构的 JSON：
{{
  "evidence_limitations": "string",
  "creative_direction": {{
    "core_concept": "string",
    "typography_advice": "string",
    "motion_advice": "string",
    "color_palette": ["#RRGGBB"]
  }},
  "background_candidates": [
    {{
      "name": "string",
      "why_it_fits": "string",
      "image_prompt_en": "string",
      "negative_prompt_en": "string",
      "recommended_loop_seconds": 12,
      "recommended_motion_strength": 0.6,
      "recommended_background_dim": 0.24
    }}
  ]
}}
"""


def score_plan(plan: dict[str, Any], candidate_count: int) -> tuple[int, list[str]]:
    score = 0
    notes: list[str] = []
    required_top = {"evidence_limitations", "creative_direction", "background_candidates"}
    if required_top.issubset(plan):
        score += 20
    else:
        notes.append("缺少顶层字段")

    limitation = str(plan.get("evidence_limitations", "")).lower()
    uncertainty_terms = ("no lyrics", "lyrics are unavailable", "unknown", "uncertain", "没有歌词", "无法确认", "信息不足")
    if any(term in limitation for term in uncertainty_terms):
        score += 15
    else:
        notes.append("没有明确承认歌词缺失和语义不确定")

    direction = plan.get("creative_direction")
    if isinstance(direction, dict) and all(
        direction.get(key) for key in ("core_concept", "typography_advice", "motion_advice", "color_palette")
    ):
        score += 10
    else:
        notes.append("总体视觉建议不完整")

    candidates = plan.get("background_candidates")
    if not isinstance(candidates, list):
        candidates = []
    if len(candidates) == candidate_count:
        score += 15
    else:
        notes.append(f"候选数量为 {len(candidates)}，期望 {candidate_count}")

    valid_parameters = 0
    constrained_prompts = 0
    usable_prompts = 0
    unique_prompts: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        prompt = str(candidate.get("image_prompt_en", ""))
        negative = str(candidate.get("negative_prompt_en", ""))
        lower = (prompt + " " + negative).lower()
        if len(prompt.split()) >= 25 and len(negative.split()) >= 5:
            usable_prompts += 1
        center_ok = any(term in lower for term in ("negative space", "low-detail center", "clean center", "empty center"))
        no_text_ok = "no text" in lower or "without text" in lower
        edge_ok = "edge" in lower or "periphery" in lower or "distant" in lower
        if center_ok and no_text_ok and edge_ok:
            constrained_prompts += 1
        try:
            loop = float(candidate.get("recommended_loop_seconds"))
            motion = float(candidate.get("recommended_motion_strength"))
            dim = float(candidate.get("recommended_background_dim"))
            if 8 <= loop <= 18 and 0 <= motion <= 1 and 0 <= dim <= 0.9:
                valid_parameters += 1
        except (TypeError, ValueError):
            pass
        unique_prompts.add(prompt.strip().lower())

    expected = max(1, candidate_count)
    score += round(15 * min(usable_prompts, expected) / expected)
    score += round(15 * min(constrained_prompts, expected) / expected)
    score += round(5 * min(valid_parameters, expected) / expected)
    if len(unique_prompts) == len(candidates) and len(candidates) > 1:
        score += 5
    else:
        notes.append("背景候选重复度偏高")
    return min(score, 100), notes


def build_report(rows: list[dict[str, Any]], model: str | None, status: str) -> str:
    lines = [
        "# AutoMV 大模型能力测试",
        "",
        f"- 状态：{status}",
        f"- 模型：{model or '未配置'}",
        f"- 样本数：{len(rows)}",
        "",
        "## 样本结果",
        "",
        "| 文件 | 时长 | 得分 | 延迟 | 备注 |",
        "|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['file']} | {row['duration']:.3f}s | {row.get('score', '未运行')} | "
            f"{row.get('latency_seconds', '—')} | {'；'.join(row.get('notes', [])) or '—'} |"
        )
    scores = [row["score"] for row in rows if isinstance(row.get("score"), int)]
    if scores:
        lines.extend(["", f"平均得分：**{sum(scores) / len(scores):.1f}/100**"])
    else:
        lines.extend(
            [
                "",
                "接口尚未配置，因此这里只完成了输入审计和测试请求生成，不能声称已经测得模型水平。",
            ]
        )
    return "\n".join(lines) + "\n"


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="批量测试大模型在无歌词阶段规划纯歌词 MV 的能力。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    value.add_argument("--songs-dir", type=Path, default=Path(r"D:\Downloads\songs"))
    value.add_argument("--output-dir", type=Path, default=Path("benchmark"))
    value.add_argument("--candidate-count", type=int, default=4)
    value.add_argument("--call-llm", action="store_true")
    value.add_argument("--endpoint", default=os.environ.get("AUTOMV_LLM_ENDPOINT"))
    value.add_argument("--model", default=os.environ.get("AUTOMV_LLM_MODEL"))
    value.add_argument("--api-key-env", default="AUTOMV_LLM_API_KEY")
    value.add_argument("--no-auth", action="store_true")
    value.add_argument("--timeout", type=float, default=120.0)
    value.add_argument("--ffprobe", type=Path)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        songs_dir = args.songs_dir.expanduser().resolve()
        output_dir = args.output_dir.expanduser().resolve()
        if not songs_dir.is_dir():
            raise FileNotFoundError(f"歌曲目录不存在：{songs_dir}")
        files = sorted(
            [path for path in songs_dir.rglob("*") if path.suffix.lower() in {".wav", ".mp3"}],
            key=lambda path: path.name.lower(),
        )
        if not files:
            raise ValueError("歌曲目录中没有 WAV 或 MP3。")
        if not 1 <= args.candidate_count <= 10:
            raise ValueError("candidate-count 必须在 1 到 10 之间。")
        if args.call_llm and (not args.endpoint or not args.model):
            raise ValueError("调用模型需要 endpoint 和 model。")
        api_key = None if args.no_auth else os.environ.get(args.api_key_env)
        if args.call_llm and not args.no_auth and not api_key:
            raise ValueError(f"缺少环境变量 {args.api_key_env}。")

        ffprobe = find_ffprobe(args.ffprobe)
        output_dir.mkdir(parents=True, exist_ok=True)
        rows: list[dict[str, Any]] = []
        for index, path in enumerate(files, start=1):
            info = probe_audio(path, ffprobe)
            prompt = build_benchmark_prompt(info, args.candidate_count)
            case_dir = output_dir / f"{index:02d}_{path.stem}"
            case_dir.mkdir(parents=True, exist_ok=True)
            (case_dir / "input.json").write_text(
                json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (case_dir / "request.md").write_text(
                f"# System\n\n{SYSTEM_PROMPT}\n\n# User\n\n{prompt}\n", encoding="utf-8"
            )
            row: dict[str, Any] = {
                "file": path.name,
                "duration": info["duration_seconds"],
                "notes": [],
            }
            if args.call_llm:
                started = time.perf_counter()
                response = call_compatible_llm(
                    endpoint=args.endpoint,
                    model=args.model,
                    api_key=api_key,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=prompt,
                    timeout=args.timeout,
                )
                row["latency_seconds"] = round(time.perf_counter() - started, 3)
                (case_dir / "raw_response.txt").write_text(response, encoding="utf-8")
                try:
                    plan = extract_json(response)
                    (case_dir / "plan.json").write_text(
                        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    row["score"], row["notes"] = score_plan(plan, args.candidate_count)
                except (ValueError, json.JSONDecodeError) as exc:
                    row["score"] = 0
                    row["notes"] = [f"JSON 解析失败：{exc}"]
            rows.append(row)

        status = "已完成模型调用" if args.call_llm else "仅完成预检，模型未调用"
        report = build_report(rows, args.model, status)
        report_path = output_dir / "report.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"测试报告：{report_path}")
        print(status)
        return 0
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
