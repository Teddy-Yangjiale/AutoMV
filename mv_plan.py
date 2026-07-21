#!/usr/bin/env python3
"""Create an LLM-ready visual brief and image prompt pack for a lyric MV."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from lyrics_mv import LyricLine, apply_offset, parse_lrc


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["project_title", "creative_direction", "background_candidates"],
    "properties": {
        "project_title": {"type": "string"},
        "creative_direction": {
            "type": "object",
            "required": [
                "core_concept",
                "mood_curve",
                "color_palette",
                "typography_advice",
                "motion_advice",
                "avoid",
            ],
            "properties": {
                "core_concept": {"type": "string"},
                "mood_curve": {"type": "array", "items": {"type": "string"}},
                "color_palette": {"type": "array", "items": {"type": "string"}},
                "typography_advice": {"type": "string"},
                "motion_advice": {"type": "string"},
                "avoid": {"type": "array", "items": {"type": "string"}},
            },
        },
        "background_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "name",
                    "why_it_fits",
                    "image_prompt_en",
                    "negative_prompt_en",
                    "recommended_loop_seconds",
                    "recommended_motion_strength",
                    "recommended_background_dim",
                ],
                "properties": {
                    "name": {"type": "string"},
                    "why_it_fits": {"type": "string"},
                    "image_prompt_en": {"type": "string"},
                    "negative_prompt_en": {"type": "string"},
                    "recommended_loop_seconds": {"type": "number"},
                    "recommended_motion_strength": {"type": "number"},
                    "recommended_background_dim": {"type": "number"},
                },
            },
        },
    },
}


SYSTEM_PROMPT = """你是一名专业的纯歌词 MV 视觉导演和生成式图像提示词设计师。
你的任务不是讲故事，而是让居中的动态歌词成为绝对视觉主体。背景只负责建立情绪、色彩和空间氛围。
请根据歌词含义设计统一、克制、可循环的静态背景方案，并输出严格 JSON。不要输出 Markdown。"""


def _format_time(seconds: float) -> str:
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes:02d}:{remainder:05.2f}"


def build_user_prompt(
    lines: list[LyricLine],
    *,
    title: str,
    artist: str,
    aspect_ratio: str,
    candidate_count: int,
    audio_profile: dict[str, Any] | None = None,
) -> str:
    lyrics = "\n".join(f"[{_format_time(line.start)}] {line.text.replace('\\N', ' / ')}" for line in lines)
    schema_text = json.dumps(PLAN_SCHEMA, ensure_ascii=False, indent=2)
    acoustic_evidence = (
        json.dumps(audio_profile, ensure_ascii=False, indent=2)
        if audio_profile
        else "未提供。不要猜测 BPM、能量曲线或声学情绪。"
    )
    return f"""请为下面这首歌设计一套纯歌词 MV 视觉方案。

歌曲：{title or '未知标题'}
歌手：{artist or '未知歌手'}
画幅：{aspect_ratio}

硬性规则：
1. 歌词始终位于画面中央，是画面的主角；背景不能抢夺注意力。
2. 每个背景图中央 45% 区域必须是低细节、低对比度的负空间，重要视觉元素放在边缘或远景。
3. 背景最后会做 8 到 18 秒的无缝缓慢缩放和漂移动画，所以构图必须适合循环，不能依赖一次性动作。
4. 图片中严禁出现任何文字、字幕、字母、logo、水印、UI 或边框。
5. 不要把每句歌词都变成一个独立故事镜头。整首歌保持同一视觉世界和色彩逻辑。
6. 人物如非必要应避免出现；如果出现，只能是远景、剪影或背影，不能依赖清晰面部和手部。
7. 输出 {candidate_count} 个可供人工选择的背景候选。image_prompt_en 和 negative_prompt_en 必须使用英文，且可以直接交给图像生成模型。
8. recommended_motion_strength 必须在 0 到 1 之间；recommended_background_dim 必须在 0 到 0.9 之间。
9. 声学画像只用于判断能量和段落起伏；歌词负责语义情感。如果二者看似冲突，明确采用“音乐表层 + 歌词深层”的统一表达，不要机械套模板。

音频声学画像：
{acoustic_evidence}

歌词时间线：
{lyrics}

严格按照以下 JSON Schema 的字段输出，不要添加 schema 中不存在的说明文字：
{schema_text}
"""


def build_request_markdown(system_prompt: str, user_prompt: str) -> str:
    return f"""# MV 视觉方案大模型请求

把下面两段内容分别作为 system prompt 和 user prompt 交给任意大模型。模型输出应保存为 `mv_plan.json`。

## System prompt

```text
{system_prompt}
```

## User prompt

```text
{user_prompt}
```
"""


def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("大模型响应中没有找到 JSON 对象。")
    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("大模型输出的顶层必须是 JSON 对象。")
    return parsed


def validate_plan(plan: dict[str, Any], candidate_count: int) -> None:
    for key in ("project_title", "creative_direction", "background_candidates"):
        if key not in plan:
            raise ValueError(f"大模型方案缺少字段：{key}")
    candidates = plan["background_candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("background_candidates 必须是非空数组。")
    if len(candidates) < candidate_count:
        print(
            f"警告：请求了 {candidate_count} 个候选，但模型只返回 {len(candidates)} 个。",
            file=sys.stderr,
        )
    required = {
        "name",
        "why_it_fits",
        "image_prompt_en",
        "negative_prompt_en",
        "recommended_loop_seconds",
        "recommended_motion_strength",
        "recommended_background_dim",
    }
    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, dict):
            raise ValueError(f"第 {index} 个背景候选不是 JSON 对象。")
        missing = required - set(candidate)
        if missing:
            raise ValueError(f"第 {index} 个背景候选缺少字段：{', '.join(sorted(missing))}")


def _chat_endpoint(base: str) -> str:
    value = base.rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    return value + "/chat/completions"


def call_compatible_llm(
    *,
    endpoint: str,
    model: str,
    api_key: str | None,
    system_prompt: str,
    user_prompt: str,
    timeout: float,
) -> str:
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        _chat_endpoint(endpoint), data=payload, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"大模型接口返回 HTTP {exc.code}：{detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接大模型接口：{exc.reason}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"无法解析兼容接口响应：{body}") from exc
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") for item in content if isinstance(item, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("大模型接口没有返回文本内容。")
    return content


def prompts_markdown(plan: dict[str, Any]) -> str:
    direction = plan.get("creative_direction", {})
    lines = [
        f"# {plan.get('project_title', 'MV 背景方案')}",
        "",
        "## 总体建议",
        "",
        str(direction.get("core_concept", "")),
        "",
    ]
    palette = direction.get("color_palette", [])
    if palette:
        lines.extend(["色板：" + "、".join(map(str, palette)), ""])
    for index, candidate in enumerate(plan.get("background_candidates", []), start=1):
        lines.extend(
            [
                f"## 候选 {index}：{candidate.get('name', '')}",
                "",
                str(candidate.get("why_it_fits", "")),
                "",
                "Image prompt:",
                "",
                "```text",
                str(candidate.get("image_prompt_en", "")),
                "```",
                "",
                "Negative prompt:",
                "",
                "```text",
                str(candidate.get("negative_prompt_en", "")),
                "```",
                "",
                "建议渲染参数：",
                "",
                f"- `--loop-seconds {candidate.get('recommended_loop_seconds', 12)}`",
                f"- `--motion-strength {candidate.get('recommended_motion_strength', 0.6)}`",
                f"- `--background-dim {candidate.get('recommended_background_dim', 0.24)}`",
                "",
            ]
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="根据 LRC 生成纯歌词 MV 视觉方案请求，并可调用兼容大模型接口。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("lrc", type=Path, help="歌曲的 LRC 文件")
    parser.add_argument("--output-dir", type=Path, default=Path("plan"), help="方案输出目录")
    parser.add_argument("--offset", type=float, default=0.0, help="音频前置延迟秒数")
    parser.add_argument("--ignore-lrc-offset", action="store_true", help="忽略 LRC 内置 offset")
    parser.add_argument("--title", help="歌曲标题；默认读取 LRC 的 ti")
    parser.add_argument("--artist", help="歌手；默认读取 LRC 的 ar")
    parser.add_argument("--aspect-ratio", default="16:9", help="背景图目标画幅")
    parser.add_argument("--candidate-count", type=int, default=4, help="背景 prompt 候选数量")
    parser.add_argument(
        "--audio-profile",
        type=Path,
        help="emotion_director.py 生成的 director.json；用于让大模型同时理解音乐能量和歌词语义",
    )
    parser.add_argument(
        "--import-plan",
        type=Path,
        help="导入手动从大模型取得的 JSON，并生成易复制的 background_prompts.md",
    )
    parser.add_argument("--call-llm", action="store_true", help="直接调用兼容 Chat Completions 接口")
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("AUTOMV_LLM_ENDPOINT"),
        help="兼容接口 base URL 或完整 /chat/completions URL",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("AUTOMV_LLM_MODEL"),
        help="模型名称",
    )
    parser.add_argument(
        "--api-key-env",
        default="AUTOMV_LLM_API_KEY",
        help="存放 API key 的环境变量名",
    )
    parser.add_argument("--no-auth", action="store_true", help="本地接口不发送 Authorization")
    parser.add_argument("--timeout", type=float, default=120.0, help="接口超时秒数")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.candidate_count < 1 or args.candidate_count > 10:
            raise ValueError("背景候选数量必须在 1 到 10 之间。")
        document = parse_lrc(args.lrc.expanduser().resolve())
        lrc_offset = 0.0 if args.ignore_lrc_offset else document.lrc_offset_seconds
        lines = apply_offset(document.lines, args.offset + lrc_offset)
        title = args.title or document.metadata.get("ti", "")
        artist = args.artist or document.metadata.get("ar", "")
        audio_profile = None
        if args.audio_profile:
            profile = json.loads(args.audio_profile.expanduser().resolve().read_text(encoding="utf-8-sig"))
            audio_profile = {
                "features": profile.get("features"),
                "sections": profile.get("sections"),
                "acousticEmotion": profile.get("recommendation", {}).get("emotion"),
                "visualBaseline": profile.get("recommendation", {}),
            }
        user_prompt = build_user_prompt(
            lines,
            title=title,
            artist=artist,
            aspect_ratio=args.aspect_ratio,
            candidate_count=args.candidate_count,
            audio_profile=audio_profile,
        )

        output_dir = args.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        request_path = output_dir / "llm_request.md"
        request_path.write_text(
            build_request_markdown(SYSTEM_PROMPT, user_prompt), encoding="utf-8"
        )
        (output_dir / "mv_plan.schema.json").write_text(
            json.dumps(PLAN_SCHEMA, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"已生成大模型请求：{request_path}")

        if args.import_plan and args.call_llm:
            raise ValueError("--import-plan 和 --call-llm 不能同时使用。")
        if args.import_plan:
            imported = extract_json(
                args.import_plan.expanduser().resolve().read_text(encoding="utf-8-sig")
            )
            validate_plan(imported, args.candidate_count)
            plan_path = output_dir / "mv_plan.json"
            plan_path.write_text(
                json.dumps(imported, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            prompts_path = output_dir / "background_prompts.md"
            prompts_path.write_text(prompts_markdown(imported), encoding="utf-8")
            print(f"已导入 MV 方案：{plan_path}")
            print(f"背景 prompts：{prompts_path}")
            return 0

        if not args.call_llm:
            print("未调用接口。可把 llm_request.md 交给任意大模型，再将结果保存为 mv_plan.json。")
            return 0
        if not args.endpoint:
            raise ValueError("调用大模型时必须提供 --endpoint 或 AUTOMV_LLM_ENDPOINT。")
        if not args.model:
            raise ValueError("调用大模型时必须提供 --model 或 AUTOMV_LLM_MODEL。")
        api_key = None if args.no_auth else os.environ.get(args.api_key_env)
        if not args.no_auth and not api_key:
            raise ValueError(
                f"没有找到 API key。请设置环境变量 {args.api_key_env}，或对本地接口使用 --no-auth。"
            )

        response_text = call_compatible_llm(
            endpoint=args.endpoint,
            model=args.model,
            api_key=api_key,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            timeout=args.timeout,
        )
        (output_dir / "llm_raw_response.txt").write_text(response_text, encoding="utf-8")
        plan = extract_json(response_text)
        validate_plan(plan, args.candidate_count)
        plan_path = output_dir / "mv_plan.json"
        plan_path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        prompts_path = output_dir / "background_prompts.md"
        prompts_path.write_text(prompts_markdown(plan), encoding="utf-8")
        print(f"MV 方案：{plan_path}")
        print(f"背景 prompts：{prompts_path}")
        return 0
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
