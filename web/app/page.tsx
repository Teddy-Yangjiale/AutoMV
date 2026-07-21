"use client";

import { ChangeEvent, MouseEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

type Ratio = "16:9" | "9:16" | "1:1";
type BackgroundKind = "gradient" | "image" | "video";
type SubtitleAlign = "left" | "center" | "right";
type SubtitleStyleId = "elegant" | "modern" | "poster" | "editorial" | "ink" | "mono" | "outline" | "neon" | "glass";
type MotionPreset = "cinematic" | "float" | "punch" | "handwritten" | "neon" | "minimal";
type DisplayMode = "single" | "stack";
type TimedLyric = { start: number; text: string };
type SectionAutomation = { start: number; end: number; motionPreset: MotionPreset; motionIntensity: number; backgroundMotionStrength?: number; accentAmount?: number };
type EmotionInfo = { acousticCharacter: string; tags?: string[]; confidence?: number };

const subtitleStyles: ReadonlyArray<{ id: SubtitleStyleId; name: string; note: string; font: string; weight: number; italic: boolean; outline: number; shadow: number; glow: number; capsule: boolean }> = [
  { id: "elegant", name: "优雅宋体", note: "电影感叙事", font: '"Noto Serif SC", "Songti SC", STSong, SimSun, serif', weight: 500, italic: false, outline: 0, shadow: 26, glow: 0, capsule: false },
  { id: "modern", name: "现代黑体", note: "干净克制", font: '"Noto Sans SC", "Microsoft YaHei", sans-serif', weight: 650, italic: false, outline: 0, shadow: 18, glow: 0, capsule: false },
  { id: "poster", name: "海报粗体", note: "强节拍冲击", font: 'Impact, "Arial Black", "Microsoft YaHei", sans-serif', weight: 900, italic: false, outline: 2, shadow: 8, glow: 0, capsule: false },
  { id: "editorial", name: "杂志衬线", note: "留白与呼吸", font: 'Didot, Bodoni MT, Georgia, "Noto Serif SC", serif', weight: 500, italic: true, outline: 0, shadow: 14, glow: 0, capsule: false },
  { id: "ink", name: "水墨楷体", note: "手写与诗意", font: 'KaiTi, STKaiti, "Noto Serif SC", serif', weight: 500, italic: false, outline: 0, shadow: 22, glow: 0, capsule: false },
  { id: "mono", name: "等宽字幕", note: "冷感电子", font: '"JetBrains Mono", Consolas, "Microsoft YaHei", monospace', weight: 600, italic: false, outline: 0, shadow: 12, glow: 0, capsule: false },
  { id: "outline", name: "空心描边", note: "高对比舞台", font: '"Arial Black", "Microsoft YaHei", sans-serif', weight: 900, italic: false, outline: 3, shadow: 0, glow: 0, capsule: false },
  { id: "neon", name: "霓虹辉光", note: "夜景氛围", font: '"Noto Sans SC", "Microsoft YaHei", sans-serif', weight: 750, italic: false, outline: 0, shadow: 8, glow: 24, capsule: false },
  { id: "glass", name: "玻璃胶囊", note: "清晰信息层", font: '"Noto Sans SC", "Microsoft YaHei", sans-serif', weight: 650, italic: false, outline: 0, shadow: 18, glow: 0, capsule: true },
];

const directions: ReadonlyArray<{ id: string; name: string; subtitle: string; colors: [string, string, string]; style: SubtitleStyleId; motion: MotionPreset; text: string; accent: string; dim: number; motionAmount: number; fontSize: number; tracking: number }> = [
  { id: "film", name: "电影呼吸", subtitle: "抒情 / 叙事", colors: ["#101827", "#81684f", "#d8b68f"], style: "elegant", motion: "cinematic", text: "#fff9ef", accent: "#d9ad7c", dim: 42, motionAmount: 12, fontSize: 58, tracking: 8 },
  { id: "chalk", name: "粉笔故事", subtitle: "童真 / 手绘", colors: ["#071b20", "#d09b68", "#8fb6c3"], style: "ink", motion: "handwritten", text: "#f4dfb7", accent: "#e49a70", dim: 24, motionAmount: 9, fontSize: 60, tracking: 6 },
  { id: "collage", name: "流行拼贴", subtitle: "明快 / 跳跃", colors: ["#103e8c", "#ef493f", "#77c8ea"], style: "poster", motion: "punch", text: "#fffaf0", accent: "#ff5548", dim: 18, motionAmount: 20, fontSize: 66, tracking: 1 },
  { id: "diary", name: "公路日记", subtitle: "旅行 / 回忆", colors: ["#0b3640", "#a57a57", "#e9dfca"], style: "ink", motion: "float", text: "#fffdf7", accent: "#e5c39d", dim: 34, motionAmount: 14, fontSize: 62, tracking: 5 },
  { id: "neon", name: "霓虹余响", subtitle: "夜景 / 律动", colors: ["#110823", "#7e2dbd", "#e144ff"], style: "neon", motion: "neon", text: "#fff7ff", accent: "#e85cff", dim: 38, motionAmount: 18, fontSize: 60, tracking: 4 },
  { id: "mono", name: "黑白留白", subtitle: "极简 / 克制", colors: ["#080808", "#3f4145", "#f0eee8"], style: "modern", motion: "minimal", text: "#f7f5ef", accent: "#d2d0c9", dim: 48, motionAmount: 5, fontSize: 54, tracking: 10 },
];

const motionPresets: ReadonlyArray<{ id: MotionPreset; name: string; note: string }> = [
  { id: "cinematic", name: "电影上浮", note: "柔和交接" },
  { id: "float", name: "水平漂移", note: "连续流动" },
  { id: "punch", name: "节拍撞入", note: "弹性缩放" },
  { id: "handwritten", name: "手写落笔", note: "轻微旋转" },
  { id: "neon", name: "霓虹聚焦", note: "模糊成像" },
  { id: "minimal", name: "极简淡化", note: "几乎静止" },
];

const sampleLyrics: TimedLyric[] = [
  { start: 0, text: "我把黄昏写进风里" },
  { start: 2.8, text: "等一场没有名字的雨" },
  { start: 5.9, text: "让此刻慢一点经过" },
  { start: 8.8, text: "下一句从上一句的方向继续" },
];

function Icon({ name }: { name: "play" | "upload" | "spark" | "layers" | "download" }) {
  const paths = {
    play: <path d="m8 5 11 7-11 7V5Z" />,
    upload: <><path d="M12 16V4m0 0L7 9m5-5 5 5"/><path d="M5 15v4h14v-4"/></>,
    spark: <><path d="m12 2 1.4 5.1L18 9l-4.6 1.9L12 16l-1.4-5.1L6 9l4.6-1.9L12 2Z"/><path d="m19 15 .7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7L19 15Z"/></>,
    layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/></>,
    download: <><path d="M12 3v12m0 0 5-5m-5 5-5-5"/><path d="M5 21h14"/></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" className="icon">{paths[name]}</svg>;
}

function parseLrc(source: string): TimedLyric[] {
  const parsed: TimedLyric[] = [];
  for (const rawLine of source.split(/\r?\n/)) {
    const matches = [...rawLine.matchAll(/\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]/g)];
    const text = rawLine.replace(/\[[^\]]+\]/g, "").trim();
    if (!text || !matches.length) continue;
    for (const match of matches) {
      const fraction = match[3] ? Number(match[3]) / 10 ** match[3].length : 0;
      parsed.push({ start: Number(match[1]) * 60 + Number(match[2]) + fraction, text });
    }
  }
  return parsed.sort((a, b) => a.start - b.start);
}

function formatTime(seconds: number) {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(Math.floor(safe % 60)).padStart(2, "0")}`;
}

export default function Home() {
  const [direction, setDirection] = useState("film");
  const [ratio, setRatio] = useState<Ratio>("16:9");
  const [background, setBackground] = useState<{ kind: BackgroundKind; url?: string }>({ kind: "gradient" });
  const [lyrics, setLyrics] = useState<TimedLyric[]>(sampleLyrics);
  const [activeLine, setActiveLine] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(11.8);
  const [dim, setDim] = useState(42);
  const [motion, setMotion] = useState(12);
  const [loopSeconds, setLoopSeconds] = useState(12);
  const [palette, setPalette] = useState<[string, string, string]>(["#101827", "#81684f", "#d8b68f"]);
  const [audioName, setAudioName] = useState("等待载入歌曲");
  const [audioUrl, setAudioUrl] = useState<string>();
  const [lrcName, setLrcName] = useState("lyrics.lrc");
  const [backgroundName, setBackgroundName] = useState("background.png");
  const [offsetSeconds, setOffsetSeconds] = useState(0);
  const [subtitleStyle, setSubtitleStyle] = useState<SubtitleStyleId>("elegant");
  const [motionPreset, setMotionPreset] = useState<MotionPreset>("cinematic");
  const [displayMode, setDisplayMode] = useState<DisplayMode>("single");
  const [fontSize, setFontSize] = useState(58);
  const [letterSpacing, setLetterSpacing] = useState(8);
  const [subtitleY, setSubtitleY] = useState(52);
  const [subtitleAlign, setSubtitleAlign] = useState<SubtitleAlign>("center");
  const [textColor, setTextColor] = useState("#fff9ef");
  const [accentColor, setAccentColor] = useState("#d9ad7c");
  const [sectionAutomation, setSectionAutomation] = useState<SectionAutomation[]>([]);
  const [emotionInfo, setEmotionInfo] = useState<EmotionInfo>();
  const [directorScore, setDirectorScore] = useState<number>();
  const audioRef = useRef<HTMLAudioElement>(null);
  const audioObjectUrl = useRef<string>();
  const backgroundObjectUrl = useRef<string>();

  const chosen = directions.find((item) => item.id === direction) ?? directions[0];
  const chosenSubtitle = subtitleStyles.find((item) => item.id === subtitleStyle) ?? subtitleStyles[0];
  const ratioClass = ratio.replace(":", "-");
  const progress = duration > 0 ? Math.min(100, currentTime / duration * 100) : 0;
  const previousLine = activeLine > 0 ? lyrics[activeLine - 1] : undefined;
  const currentLine = activeLine >= 0 ? lyrics[activeLine] : undefined;
  const nextLine = activeLine >= 0 && activeLine + 1 < lyrics.length ? lyrics[activeLine + 1] : undefined;
  const lineDuration = currentLine
    ? Math.min(6, Math.max(1.4, (nextLine?.start ?? currentLine.start + 3.2) - currentLine.start))
    : 2;
  const lyricTime = currentTime - offsetSeconds;
  const activeAutomation = sectionAutomation.find((item) => item.start <= lyricTime && lyricTime < item.end);
  const effectiveMotionPreset = activeAutomation?.motionPreset ?? motionPreset;

  const updateActiveLine = useCallback((audioTime: number, lyricOffset = offsetSeconds) => {
    const lyricTime = audioTime - lyricOffset;
    let index = -1;
    for (let i = 0; i < lyrics.length; i += 1) {
      if (lyrics[i].start <= lyricTime) index = i;
      else break;
    }
    setActiveLine(index);
  }, [lyrics, offsetSeconds]);

  useEffect(() => () => {
    if (audioObjectUrl.current) URL.revokeObjectURL(audioObjectUrl.current);
    if (backgroundObjectUrl.current) URL.revokeObjectURL(backgroundObjectUrl.current);
  }, []);

  useEffect(() => {
    if (!playing || audioUrl) return;
    const timer = window.setInterval(() => {
      setCurrentTime((value) => {
        const next = value + 0.05 >= duration ? 0 : value + 0.05;
        updateActiveLine(next);
        return next;
      });
    }, 50);
    return () => window.clearInterval(timer);
  }, [playing, audioUrl, duration, updateActiveLine]);

  const backgroundStyle = useMemo(() => {
    if (background.kind === "image" && background.url) return { backgroundImage: `url(${background.url})` };
    return { backgroundImage: `radial-gradient(circle at 24% 18%, ${palette[2]}44, transparent 30%), radial-gradient(circle at 76% 80%, ${palette[1]}55, transparent 36%), linear-gradient(145deg, ${palette[0]}, #06070a 76%)` };
  }, [background, palette]);

  function applyDirection(id: string) {
    const preset = directions.find((item) => item.id === id);
    if (!preset) return;
    setDirection(id);
    setPalette([...preset.colors]);
    setSubtitleStyle(preset.style);
    setMotionPreset(preset.motion);
    setTextColor(preset.text);
    setAccentColor(preset.accent);
    setDim(preset.dim);
    setMotion(preset.motionAmount);
    setFontSize(preset.fontSize);
    setLetterSpacing(preset.tracking);
  }

  function chooseAudio(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (audioObjectUrl.current) URL.revokeObjectURL(audioObjectUrl.current);
    const url = URL.createObjectURL(file);
    audioObjectUrl.current = url;
    setAudioUrl(url);
    setAudioName(file.name);
    setPlaying(false);
    setCurrentTime(0);
  }

  function chooseBackground(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (backgroundObjectUrl.current) URL.revokeObjectURL(backgroundObjectUrl.current);
    const url = URL.createObjectURL(file);
    backgroundObjectUrl.current = url;
    setBackgroundName(file.name);
    setBackground({ kind: file.type.startsWith("video/") ? "video" : "image", url });
  }

  function chooseLyrics(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setLrcName(file.name);
    const reader = new FileReader();
    reader.onload = () => {
      const parsed = parseLrc(String(reader.result ?? ""));
      if (parsed.length) {
        setLyrics(parsed);
        setActiveLine(offsetSeconds > 0 ? -1 : 0);
        setCurrentTime(0);
        if (!audioUrl) setDuration(Math.max(8, parsed.at(-1)!.start + 3));
      }
    };
    reader.readAsText(file);
  }

  function chooseDirector(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const profile = JSON.parse(String(reader.result ?? "{}"));
        const recommendation = profile.recommendation;
        if (!recommendation || typeof recommendation !== "object") throw new Error("missing recommendation");
        if (directions.some((item) => item.id === recommendation.visualDirection)) applyDirection(recommendation.visualDirection);
        const recommendedBackground = recommendation.background ?? {};
        if (Array.isArray(recommendedBackground.colors) && recommendedBackground.colors.length === 3) setPalette(recommendedBackground.colors);
        if (Number.isFinite(recommendedBackground.dim)) setDim(Math.round(recommendedBackground.dim * 100));
        if (Number.isFinite(recommendedBackground.motionStrength)) setMotion(Math.round(recommendedBackground.motionStrength * 30));
        if (Number.isFinite(recommendedBackground.loopSeconds)) setLoopSeconds(recommendedBackground.loopSeconds);
        const recommendedSubtitles = recommendation.subtitles ?? {};
        if (subtitleStyles.some((item) => item.id === recommendedSubtitles.style)) setSubtitleStyle(recommendedSubtitles.style);
        if (motionPresets.some((item) => item.id === recommendedSubtitles.motionPreset)) setMotionPreset(recommendedSubtitles.motionPreset);
        if (recommendedSubtitles.displayMode === "single" || recommendedSubtitles.displayMode === "stack") setDisplayMode(recommendedSubtitles.displayMode);
        if (Number.isFinite(recommendedSubtitles.fontSize)) setFontSize(recommendedSubtitles.fontSize);
        if (Number.isFinite(recommendedSubtitles.letterSpacingEm)) setLetterSpacing(Math.round(recommendedSubtitles.letterSpacingEm * 100));
        if (Number.isFinite(recommendedSubtitles.yPercent)) setSubtitleY(recommendedSubtitles.yPercent);
        if (["left", "center", "right"].includes(recommendedSubtitles.align)) setSubtitleAlign(recommendedSubtitles.align);
        if (recommendedSubtitles.textColor) setTextColor(recommendedSubtitles.textColor);
        if (recommendedSubtitles.accentColor) setAccentColor(recommendedSubtitles.accentColor);
        const automation = Array.isArray(recommendation.sectionAutomation) ? recommendation.sectionAutomation : [];
        setSectionAutomation(automation.filter((item: SectionAutomation) => motionPresets.some((preset) => preset.id === item.motionPreset)));
        setEmotionInfo(recommendation.emotion);
        if (Number.isFinite(profile.evaluation?.overallScore)) setDirectorScore(profile.evaluation.overallScore);
      } catch {
        window.alert("无法读取情感导演配置，请选择 emotion_director.py 生成的 director.json。");
      }
    };
    reader.readAsText(file);
  }

  async function togglePlayback() {
    if (audioRef.current && audioUrl) {
      if (audioRef.current.paused) {
        await audioRef.current.play();
        setPlaying(true);
      } else {
        audioRef.current.pause();
        setPlaying(false);
      }
      return;
    }
    setPlaying((value) => !value);
  }

  function seek(event: MouseEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const target = Math.max(0, Math.min(duration, (event.clientX - rect.left) / rect.width * duration));
    if (audioRef.current && audioUrl) audioRef.current.currentTime = target;
    setCurrentTime(target);
    updateActiveLine(target);
  }

  function downloadProject() {
    const dimensions = ratio === "16:9" ? [1920, 1080] : ratio === "9:16" ? [1080, 1920] : [1080, 1080];
    const project = {
      version: 1,
      audio: { file: audioName === "等待载入歌曲" ? "song.wav" : audioName, offsetSeconds },
      lyrics: { file: lrcName },
      canvas: { ratio, width: dimensions[0], height: dimensions[1], fps: 30 },
      visualDirection: direction,
      emotionDirector: emotionInfo ? { ...emotionInfo, sourceScore: directorScore } : null,
      sectionAutomation,
      background: { kind: background.kind, file: background.kind === "gradient" ? null : backgroundName, colors: palette, dim: dim / 100, motionStrength: motion / 30, loopSeconds },
      subtitles: { style: subtitleStyle, motionPreset, displayMode, fontFamily: chosenSubtitle.font, fontSize, letterSpacingEm: letterSpacing / 100, yPercent: subtitleY, align: subtitleAlign, textColor, accentColor, showContext: displayMode === "stack" },
      render: { crf: 18, preset: "medium", audioBitrate: "320k" },
    };
    const blobUrl = URL.createObjectURL(new Blob([JSON.stringify(project, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = "automv-project.json";
    link.click();
    URL.revokeObjectURL(blobUrl);
  }

  const canvasVariables = {
    "--dim": dim / 100,
    "--motion": `${Math.max(1, motion / 10)}s`,
    "--line-duration": `${lineDuration}s`,
    "--subtitle-size": `${fontSize}px`,
    "--subtitle-tracking": `${letterSpacing / 100}em`,
    "--subtitle-y": `${subtitleY}%`,
    "--subtitle-color": textColor,
    "--subtitle-accent": accentColor,
    "--subtitle-outline": `${chosenSubtitle.outline}px`,
    "--subtitle-shadow": `${chosenSubtitle.shadow}px`,
    "--subtitle-glow": `${chosenSubtitle.glow}px`,
    "--subtitle-font": chosenSubtitle.font,
    "--subtitle-weight": chosenSubtitle.weight,
    "--subtitle-style": chosenSubtitle.italic ? "italic" : "normal",
    "--subtitle-align": subtitleAlign,
    "--subtitle-flex": subtitleAlign === "left" ? "flex-start" : subtitleAlign === "right" ? "flex-end" : "center",
  } as React.CSSProperties;

  return (
    <main className="studio-shell">
      <audio ref={audioRef} src={audioUrl} onTimeUpdate={(event) => { const time = event.currentTarget.currentTime; setCurrentTime(time); updateActiveLine(time); }} onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
      <header className="topbar">
        <a className="brand" href="#" aria-label="AutoMV Studio home"><span className="brand-mark">A</span><span>AutoMV <b>Studio</b></span></a>
        <div className="project-title"><span className="status-dot" />逐句动效设计 <span className="saved">LRC 时间驱动</span></div>
        <div className="top-actions"><button className="ghost-button">设计基准</button><button className="export-button" onClick={downloadProject}><Icon name="download" /> 导出配置</button></div>
      </header>

      <section className="workspace">
        <aside className="panel left-panel">
          <div className="panel-heading"><div><span className="eyebrow">VISUAL DIRECTION</span><h2>成片视觉方向</h2></div><button className="icon-button"><Icon name="spark" /></button></div>
          <p className="panel-intro">每个方向会一起改变字体、配色、遮罩和句子运动。</p>
          <div className="template-grid">
            {directions.map((item) => (
              <button key={item.id} className={`template-card ${direction === item.id ? "selected" : ""}`} onClick={() => applyDirection(item.id)}>
                <span className="template-swatch" style={{ background: `linear-gradient(135deg, ${item.colors[0]}, ${item.colors[1]} 58%, ${item.colors[2]})` }}><i style={{ color: item.text }}>字</i><em style={{ background: item.accent }} /></span>
                <span><b>{item.name}</b><small>{item.subtitle}</small></span>
              </button>
            ))}
          </div>

          <div className="divider" />
          <div className="section-title"><span><Icon name="upload" /> 素材</span><small>本地处理，不上传</small></div>
          <label className="upload-row"><span className="file-kind audio">♪</span><span><b>歌曲音频</b><small>{audioName}</small></span><input type="file" accept="audio/mp3,audio/wav,audio/*" onChange={chooseAudio} /><em>选择</em></label>
          <label className="upload-row"><span className="file-kind">L</span><span><b>LRC 歌词</b><small>{lyrics === sampleLyrics ? "使用带时间示例" : `${lyrics.length} 句已载入`}</small></span><input type="file" accept=".lrc,text/plain" onChange={chooseLyrics} /><em>选择</em></label>
          <label className="upload-row"><span className="file-kind image">▧</span><span><b>背景素材</b><small>图片或循环视频</small></span><input type="file" accept="image/*,video/*" onChange={chooseBackground} /><em>选择</em></label>
          <label className={`upload-row ${emotionInfo ? "director-loaded" : ""}`}><span className="file-kind director">D</span><span><b>情感导演</b><small>{emotionInfo ? `${emotionInfo.acousticCharacter} · ${sectionAutomation.length} 个段落` : "导入 director.json"}</small></span><input type="file" accept=".json,application/json" onChange={chooseDirector} /><em>{emotionInfo ? "已应用" : "选择"}</em></label>
          <label className="number-field"><span><b>歌曲开始时间 x</b><small>预览与成片同时应用</small></span><div><input type="number" min="0" step="0.01" value={offsetSeconds} onChange={(event) => { const value = Number(event.target.value); setOffsetSeconds(value); updateActiveLine(currentTime, value); }} /><em>秒</em></div></label>

          <div className="divider" />
          <div className="section-title"><span><Icon name="layers" /> 画布</span></div>
          <div className="segmented">{(["16:9", "9:16", "1:1"] as Ratio[]).map((item) => <button key={item} onClick={() => setRatio(item)} className={ratio === item ? "active" : ""}>{item}</button>)}</div>
        </aside>

        <section className="stage-area">
          <div className="stage-toolbar"><span className="live-pill"><i /> LRC 同步预览</span><span>{emotionInfo?.acousticCharacter ?? `${ratio} · 1080P`}</span><span className="motion-readout">{motionPresets.find((item) => item.id === effectiveMotionPreset)?.name}</span></div>
          <div className={`canvas-wrap ratio-${ratioClass}`}>
            <div className={`mv-canvas direction-${direction} subtitle-${subtitleStyle} motion-${effectiveMotionPreset} mode-${displayMode}`} style={canvasVariables}>
              {background.kind === "video" && background.url ? <video className="background-media" src={background.url} autoPlay muted loop playsInline /> : <div className="background-media generated" style={backgroundStyle} />}
              <div className="background-grade" />
              <div className="film-grain" />
              <div className={`lyric-stage ${chosenSubtitle.capsule ? "with-capsule" : ""}`}>
                <span className="lyric-kicker">{chosen.name} · {activeLine >= 0 ? String(activeLine + 1).padStart(2, "0") : "INTRO"}</span>
                {displayMode === "stack" && previousLine && <p key={`previous-${activeLine}`} className="context previous-context"><span>{previousLine.text}</span></p>}
                {currentLine
                  ? <p key={`current-${activeLine}-${currentLine.text}`} className="current"><span>{currentLine.text}</span></p>
                  : <p className="waiting-line"><span>等待歌曲开始</span></p>}
                {displayMode === "single" && previousLine && <p key={`leaving-${activeLine}`} className="leaving"><span>{previousLine.text}</span></p>}
                {displayMode === "stack" && nextLine && <p key={`next-${activeLine}`} className="context next-context"><span>{nextLine.text}</span></p>}
                <span className="lyric-rule" />
              </div>
              <span className="timecode">{formatTime(currentTime)} · {activeLine >= 0 ? String(activeLine + 1).padStart(2, "0") : "--"}/{String(lyrics.length).padStart(2, "0")}</span>
            </div>
          </div>
          <div className="transport">
            <button className={`play-button ${playing ? "playing" : ""}`} onClick={togglePlayback} aria-label={playing ? "暂停" : "播放"}>{playing ? <span>Ⅱ</span> : <Icon name="play" />}</button>
            <span>{formatTime(currentTime)}</span><div className="timeline" onClick={seek} role="slider" aria-label="播放进度" aria-valuemin={0} aria-valuemax={Math.round(duration)} aria-valuenow={Math.round(currentTime)}><i style={{ width: `${progress}%` }} /><b style={{ left: `${progress}%` }} />{lyrics.map((line) => <em key={line.start} style={{ left: `${Math.min(100, (line.start + offsetSeconds) / duration * 100)}%` }} />)}</div><span>{formatTime(duration)}</span><button className="sound-button">⌁</button>
          </div>
        </section>

        <aside className="panel right-panel">
          <div className="panel-heading"><div><span className="eyebrow">KINETIC TYPE</span><h2>逐句运动</h2></div><span className="auto-badge">SYNC</span></div>
          <div className="section-title"><span>显示逻辑</span><small>正式成片默认单句</small></div>
          <div className="segmented mode-control">{(["single", "stack"] as DisplayMode[]).map((mode) => <button key={mode} onClick={() => setDisplayMode(mode)} className={displayMode === mode ? "active" : ""}>{mode === "single" ? "逐句交接" : "前后文堆叠"}</button>)}</div>
          <div className="motion-grid">{motionPresets.map((item) => <button key={item.id} onClick={() => setMotionPreset(item.id)} className={motionPreset === item.id ? "selected" : ""}><b>{item.name}</b><small>{item.note}</small></button>)}</div>
          <div className="continuity-note"><i /><span><b>{sectionAutomation.length ? `情感段落自动化 · ${sectionAutomation.length} 段` : "连续交接已启用"}</b><small>{activeAutomation ? `当前强度 ${Math.round(activeAutomation.motionIntensity * 100)}%，随音乐段落切换。` : "上一句沿当前方向离场，新句承接同一运动轴进入。"}</small></span></div>
          <div className="divider" />
          <div className="section-title"><span>背景与可读性</span></div>
          <Control label="背景压暗" value={dim} min={0} max={80} suffix="%" onChange={setDim} />
          <Control label="背景运动" value={motion} min={0} max={30} suffix="" onChange={setMotion} />
          <div className="divider" />
          <div className="section-title"><span>字幕字体</span><small>9 种风格</small></div>
          <div className="subtitle-style-grid">
            {subtitleStyles.map((style) => <button key={style.id} title={style.note} className={subtitleStyle === style.id ? "selected" : ""} onClick={() => setSubtitleStyle(style.id)} style={{ fontFamily: style.font, fontStyle: style.italic ? "italic" : "normal", fontWeight: style.weight }}><b>Aa 字</b><small>{style.name}</small></button>)}
          </div>
          <div className="style-summary"><div className={`font-preview subtitle-${subtitleStyle}`}>Aa</div><span><b>{chosenSubtitle.name}</b><small>{chosenSubtitle.note} · {fontSize} px</small></span></div>
          <Control label="字号" value={fontSize} min={28} max={88} suffix=" px" onChange={setFontSize} />
          <Control label="字间距" value={letterSpacing} min={-4} max={28} suffix="%" onChange={setLetterSpacing} />
          <Control label="纵向位置" value={subtitleY} min={24} max={78} suffix="%" onChange={setSubtitleY} />
          <div className="compact-row"><span>对齐</span><div className="align-buttons">{(["left", "center", "right"] as SubtitleAlign[]).map((align) => <button key={align} className={subtitleAlign === align ? "active" : ""} style={{ textAlign: align }} onClick={() => setSubtitleAlign(align)} aria-label={`字幕${align === "left" ? "左" : align === "right" ? "右" : "居中"}对齐`}>≡</button>)}</div></div>
          <div className="color-row"><label><span>文字</span><input type="color" value={textColor} onChange={(event) => setTextColor(event.target.value)} /></label><label><span>强调色</span><input type="color" value={accentColor} onChange={(event) => setAccentColor(event.target.value)} /></label></div>
          <div className="render-note"><Icon name="spark" /><p><b>同一份运动配置用于最终渲染</b><span>网页负责设计预览，FFmpeg + ASS 按 LRC 逐句生成正式视频。</span></p></div>
        </aside>
      </section>
    </main>
  );
}

function Control({ label, value, min, max, suffix, onChange }: { label: string; value: number; min: number; max: number; suffix: string; onChange: (value: number) => void }) {
  return <label className="control"><span><b>{label}</b><output>{value}{suffix}</output></span><input type="range" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} /></label>;
}
