# 字幕与背景如何合成

AutoMV 不使用浏览器录屏。网页只负责设计与即时预览，最终成片由 `lyrics_mv.py` 调用 FFmpeg 和 libass 逐帧渲染。

## 图层顺序

```text
04  ASS 字幕：字体、描边、阴影、辉光、淡入淡出、定位
03  可读性层：黑色透明遮罩
02  画面处理：裁切、调色、暗角、轻颗粒
01  背景源：静态图、循环视频或自动渐变
00  原始 MP3/WAV：只参与最终封装，不被网页重采样
```

FFmpeg 的核心视频滤镜链是：

```text
背景 scale/crop/fps
→ eq 调色
→ drawbox 压暗
→ vignette 暗角
→ ass=captions.ass:fontsdir=fonts
→ format=yuv420p
```

因此歌词不是预先画进背景，也不要求图片模型生成文字。背景可以随时替换，字幕时间、字体和样式仍然独立可改。

## 三种背景

- 图片：先按目标画幅等比放大和裁切，再用周期正弦函数做缩放/漂移。周期末状态和周期初状态一致，不会突然跳回。
- 视频：使用 `-stream_loop -1` 循环读取，再统一裁切、帧率、调色、压暗和暗角。最好输入本身就是首尾衔接的循环动画。
- 自动渐变：没有背景素材时生成深色渐变，适合先校对 LRC 和 offset。

## Studio 到最终渲染

1. 在 `web` 中选择歌曲、LRC、背景与字幕样式。
2. 点击“导出配置”，得到 `automv-project.json`。
3. 把 JSON 与其中引用的素材放在同一目录，文件名保持一致。
4. 运行：

```powershell
python render_project.py automv-project.json -o outputs\final.mp4
```

先只检查渲染命令和 ASS：

```powershell
python render_project.py automv-project.json -o outputs\preview.mp4 --dry-run --keep-temp
```

项目 JSON 保存的是相对文件名，不包含浏览器的 `blob:` 地址，也不会把本地音频上传到网页服务。

## 字体说明

Studio 中的 CSS 字体栈用于快速预览；最终导出以 FFmpeg/libass 能读取的字体为准。正式成片建议显式提供字体文件和内部家族名：

```powershell
python lyrics_mv.py song.wav lyrics.lrc --offset 0 `
  --font-file fonts\MyFont.otf --font-name "My Font Family" `
  --subtitle-style editorial -o outputs\final.mp4
```

这样换电脑或部署后仍能得到一致画面，也能规避字体授权和系统字体差异。
