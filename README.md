# 纯歌词 MV 生成器

现在包含两部分：

- `web/`：参考 PV 编辑器工作流实现的 AutoMV Studio，用于导入素材、选择模板、实时设计字幕并导出项目 JSON。
- `lyrics_mv.py` / `render_project.py`：权威 FFmpeg 渲染端，负责 offset、ASS 字幕、背景循环、音频封装和最终 MP4。

启动 Studio：

```powershell
cd web
pnpm install
pnpm dev
```

在 Studio 点击“导出配置”后，将 JSON 与歌曲、LRC、背景素材放在同一目录，然后运行：

```powershell
python render_project.py automv-project.json -o outputs\final.mp4
```

字幕与背景的逐层合成方式见 [`docs/COMPOSITING.md`](docs/COMPOSITING.md)，世界级歌词 MV 的案例研究、设计规则和验收门槛见 [`docs/LYRIC_VIDEO_BENCHMARK.md`](docs/LYRIC_VIDEO_BENCHMARK.md)。

让视觉先贴合音乐情感：

```powershell
python emotion_director.py "D:\Downloads\songs\月光(1).wav" `
  --offset 0 --output-dir benchmark\emotion
```

把生成的 `*.director.json` 导入 Studio，即可应用声学情感基线和段落级运动变化。完整原理、八维评分和样片验收方法见 [`docs/EMOTION_MATCHING.md`](docs/EMOTION_MATCHING.md)，当前六首输入的审计见 [`docs/CURRENT_MV_AUDIT.md`](docs/CURRENT_MV_AUDIT.md)。

输入一份 `MP3/WAV` 音频、一份与歌曲本体对齐的 `LRC`，以及歌曲在音频中的已知开始时间 `x`，输出带动态背景和居中歌词动画的 `MP4`。

推荐使用两阶段工作流：

```text
LRC → 大模型视觉建议和背景 prompts → 人工生成/选择背景图
                                           ↓
音频 + LRC + offset + 背景图 → 无缝循环动画 + 居中歌词 → MP4
```

歌词始终是画面主体。给大模型的约束会要求背景中央保留低细节负空间、禁止图片内文字和水印，并保持全曲视觉统一。

例如歌曲本身的第一句歌词发生在第 `0.00` 秒，但处理后的 WAV 前面多出了 `3.25` 秒静音，则传入 `--offset 3.25`。程序会把所有 LRC 时间统一增加 `3.25` 秒，音频本身不会被裁剪或移动。

## 环境准备

需要 Python 3.10 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 第一步：生成 MV 建议和背景 prompts

### 还没有 LRC 时：先测试大模型

可以先用歌曲文件名和音频技术信息测试模型是否严谨，不要求字幕文件：

```powershell
python llm_benchmark.py `
  --songs-dir "D:\Downloads\songs" `
  --output-dir benchmark
```

未配置接口时，这条命令只会为每首歌生成独立测试请求和预检报告。配置兼容接口后执行真实测试：

```powershell
$env:AUTOMV_LLM_ENDPOINT = "https://你的服务地址/v1"
$env:AUTOMV_LLM_MODEL = "你的模型名"
$env:AUTOMV_LLM_API_KEY = "你的密钥"

python llm_benchmark.py `
  --songs-dir "D:\Downloads\songs" `
  --output-dir benchmark `
  --call-llm
```

报告会检查 JSON 稳定性、是否承认歌词缺失、是否编造歌曲含义、背景候选数量、中央留白约束、图片 prompt 可用性、循环参数范围和候选差异度。每首歌满分 100 分。

只生成一份可以粘贴给任意大模型的请求文件，不需要 API：

```powershell
python mv_plan.py lyrics.lrc --offset 3.25 --output-dir plan
```

输出：

- `plan/llm_request.md`：完整的 system prompt 和 user prompt。
- `plan/mv_plan.schema.json`：要求大模型返回的结构。

把请求交给你使用的大模型，将模型返回的 JSON 保存为 `plan/mv_plan.json`。它会给出整体 MV 建议、色板、排版建议、运动建议，以及默认四组英文背景图 prompts。

把手动取得的 JSON 转成便于复制的 prompt 文档：

```powershell
python mv_plan.py lyrics.lrc --offset 3.25 --output-dir plan `
  --import-plan plan\mv_plan.json
```

如果使用兼容 Chat Completions 的在线或本地大模型接口，可以直接调用：

```powershell
$env:AUTOMV_LLM_ENDPOINT = "https://你的服务地址/v1"
$env:AUTOMV_LLM_MODEL = "你的模型名"
$env:AUTOMV_LLM_API_KEY = "你的密钥"

python mv_plan.py lyrics.lrc --offset 3.25 --output-dir plan --call-llm
```

本地无鉴权接口使用 `--no-auth`。成功后还会生成 `background_prompts.md`，方便直接复制 prompt 到图像生成工具。

让图像模型生成背景时，建议：

- 横屏生成 16:9，竖屏生成 9:16。
- 不要让模型生成歌词，歌词由本程序渲染。
- 画面中央保持低对比度和低细节。
- 从四个候选里人工挑选一张构图最稳定的图片。
- 将选中的图片保存为 PNG、JPG、WebP 或 BMP。

`imageio-ffmpeg` 会提供带 `libass` 的 FFmpeg。如果电脑已经安装了完整 FFmpeg，程序会优先使用系统版本。也可以用 `--ffmpeg` 指定可执行文件，或设置环境变量 `LYRICS_MV_FFMPEG`。

## 最简单的用法

```powershell
python lyrics_mv.py song.wav lyrics.lrc --offset 3.25 -o output.mp4
```

使用人工选择的 AI 背景图：

```powershell
python lyrics_mv.py song.wav lyrics.lrc `
  --offset 3.25 `
  --background-image background.png `
  --loop-seconds 12 `
  --motion-strength 0.6 `
  --background-dim 0.24 `
  -o output.mp4
```

背景动画采用周期函数：循环结束时会回到和开头相同的缩放与位置状态，因此可以持续播放，不会在每 12 秒突然跳回。`--motion-strength 0` 可以关闭运动；`--background-dim` 越大，背景越暗、歌词越突出。

覆盖已有输出：

```powershell
python lyrics_mv.py song.mp3 lyrics.lrc --offset 2.0 -o output.mp4 --overwrite
```

如果音频没有前置延迟，也仍然明确传入：

```powershell
python lyrics_mv.py song.mp3 lyrics.lrc --offset 0
```

未指定 `-o` 时，默认输出为音频同目录下的 `原文件名_lyrics_mv.mp4`。

## 时间偏移规则

最终字幕时间为：

```text
最终时间 = LRC 时间 + --offset 秒 + LRC 文件内的 [offset:毫秒]
```

如果不想使用 LRC 自带的 `[offset:]`，增加 `--ignore-lrc-offset`。

## LRC 支持范围

支持：

- `[mm:ss]`、`[mm:ss.xx]` 和 `[mm:ss.xxx]`。
- 同一行多个时间戳，例如 `[00:10.00][01:20.00]重复副歌`。
- `[ti:]`、`[ar:]`、`[al:]`、`[offset:]` 等元数据。
- UTF-8、UTF-8 BOM、GB18030 和 UTF-16 编码。
- 同一时间戳的双语歌词；两行会合并显示。

普通 LRC 只有逐行起始时间，因此当前版本做逐行淡入、轻微放大和淡出，不虚构逐字时间。若以后需要逐字卡拉 OK，应当输入增强型 LRC 或单独的逐字时间 JSON。

## 常用视觉参数

竖屏版本：

```powershell
python lyrics_mv.py song.wav lyrics.lrc --offset 3.25 `
  --width 1080 --height 1920 --font-size 68 -o vertical.mp4
```

自定义颜色：

```powershell
python lyrics_mv.py song.wav lyrics.lrc --offset 3.25 `
  --text-color "#FFF8EE" `
  --accent-color "#FFB36B" `
  --background-colors "#120A0F" "#37131B" "#10172E" `
  -o warm.mp4
```

只显示当前歌词，不显示淡化的前后句：

```powershell
python lyrics_mv.py song.wav lyrics.lrc --offset 3.25 `
  --display-mode single --motion-preset cinematic -o clean.mp4
```

正式歌词 MV 默认采用逐句显示。可选动效为 `cinematic`、`float`、`punch`、`handwritten`、`neon` 和 `minimal`；需要同时显示淡化的前后句时使用 `--display-mode stack`。旧参数 `--no-context` 仍保留兼容性。

如果没有提供 `--background-image`，程序仍会自动生成深色动态渐变背景，适合快速预览字幕和 offset。

自定义中文字体：

```powershell
python lyrics_mv.py song.wav lyrics.lrc --offset 3.25 `
  --font-file "D:\Fonts\MyFont.ttf" --font-name "My Font Family" `
  -o custom-font.mp4
```

`--font-name` 必须是字体文件内部的字体家族名，不一定等于文件名。Windows 会优先选择更适合优雅歌词排版的 `Noto Serif SC`，其次回退到 `Noto Sans SC`、微软雅黑、黑体或宋体。

## 画质与输出

默认输出：

- 1920×1080、30 FPS。
- H.264，CRF 18。
- AAC 320 kbps。
- `yuv420p`，兼容常见播放器和视频平台。
- `faststart`，便于网页端边下载边播放。

快速预览可以使用：

```powershell
python lyrics_mv.py song.wav lyrics.lrc --offset 3.25 `
  --width 1280 --height 720 --preset veryfast --crf 23 -o preview.mp4
```

正式导出再使用默认的 `1920×1080 / CRF 18 / medium`。

## 调试

保留生成的 `captions.ass` 和 `manifest.json`：

```powershell
python lyrics_mv.py song.wav lyrics.lrc --offset 3.25 --keep-temp -o output.mp4
```

调试目录会创建在输出旁边，名称为 `output_render_files`。`manifest.json` 会记录最终偏移和每句歌词的绝对时间。

查看完整参数：

```powershell
python lyrics_mv.py --help
```

运行测试：

```powershell
python -m unittest discover -s tests -v
```
