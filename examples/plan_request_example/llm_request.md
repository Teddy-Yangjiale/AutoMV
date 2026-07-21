# MV 视觉方案大模型请求

把下面两段内容分别作为 system prompt 和 user prompt 交给任意大模型。模型输出应保存为 `mv_plan.json`。

## System prompt

```text
你是一名专业的纯歌词 MV 视觉导演和生成式图像提示词设计师。
你的任务不是讲故事，而是让居中的动态歌词成为绝对视觉主体。背景只负责建立情绪、色彩和空间氛围。
请根据歌词含义设计统一、克制、可循环的静态背景方案，并输出严格 JSON。不要输出 Markdown。
```

## User prompt

```text
请为下面这首歌设计一套纯歌词 MV 视觉方案。

歌曲：纯歌词 MV 示例
歌手：Demo
画幅：16:9

硬性规则：
1. 歌词始终位于画面中央，是画面的主角；背景不能抢夺注意力。
2. 每个背景图中央 45% 区域必须是低细节、低对比度的负空间，重要视觉元素放在边缘或远景。
3. 背景最后会做 8 到 18 秒的无缝缓慢缩放和漂移动画，所以构图必须适合循环，不能依赖一次性动作。
4. 图片中严禁出现任何文字、字幕、字母、logo、水印、UI 或边框。
5. 不要把每句歌词都变成一个独立故事镜头。整首歌保持同一视觉世界和色彩逻辑。
6. 人物如非必要应避免出现；如果出现，只能是远景、剪影或背影，不能依赖清晰面部和手部。
7. 输出 4 个可供人工选择的背景候选。image_prompt_en 和 negative_prompt_en 必须使用英文，且可以直接交给图像生成模型。
8. recommended_motion_strength 必须在 0 到 1 之间；recommended_background_dim 必须在 0 到 0.9 之间。

歌词时间线：
[00:02.00] 这是第一句歌词
[00:04.50] 字幕会统一加上音频延迟
[00:07.20] 背景保持简洁
[00:09.80] 让歌词成为画面的主体

严格按照以下 JSON Schema 的字段输出，不要添加 schema 中不存在的说明文字：
{
  "type": "object",
  "required": [
    "project_title",
    "creative_direction",
    "background_candidates"
  ],
  "properties": {
    "project_title": {
      "type": "string"
    },
    "creative_direction": {
      "type": "object",
      "required": [
        "core_concept",
        "mood_curve",
        "color_palette",
        "typography_advice",
        "motion_advice",
        "avoid"
      ],
      "properties": {
        "core_concept": {
          "type": "string"
        },
        "mood_curve": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "color_palette": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "typography_advice": {
          "type": "string"
        },
        "motion_advice": {
          "type": "string"
        },
        "avoid": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      }
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
          "recommended_background_dim"
        ],
        "properties": {
          "name": {
            "type": "string"
          },
          "why_it_fits": {
            "type": "string"
          },
          "image_prompt_en": {
            "type": "string"
          },
          "negative_prompt_en": {
            "type": "string"
          },
          "recommended_loop_seconds": {
            "type": "number"
          },
          "recommended_motion_strength": {
            "type": "number"
          },
          "recommended_background_dim": {
            "type": "number"
          }
        }
      }
    }
  }
}

```
