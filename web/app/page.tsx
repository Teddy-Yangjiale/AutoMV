"use client";

import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";

type Ratio = "16:9" | "9:16" | "1:1";
type BackgroundKind = "gradient" | "image" | "video";
type SubtitleAlign = "left" | "center" | "right";

const templates = [
  { id: "film", name: "情绪电影", subtitle: "克制 / 叙事", colors: ["#17243f", "#d6a97d"] },
  { id: "impact", name: "蓝色冲击", subtitle: "节拍 / 闪切", colors: ["#0a39ff", "#5ce1ff"] },
  { id: "editorial", name: "杂志留白", subtitle: "优雅 / 人声", colors: ["#d8d1c5", "#6d5549"] },
  { id: "neon", name: "霓虹余响", subtitle: "夜景 / 律动", colors: ["#120b25", "#e144ff"] },
  { id: "paper", name: "纸上诗歌", subtitle: "民谣 / 轻柔", colors: ["#bfae96", "#ede3d3"] },
  { id: "mono", name: "黑白宣言", subtitle: "极简 / 强烈", colors: ["#080808", "#f4f4ef"] },
] as const;

const sampleLyrics = ["我把黄昏写进风里", "等一场没有名字的雨", "让此刻慢一点经过"];

const subtitleStyles = [
  { id: "elegant", name: "优雅宋体", note: "电影感叙事", font: '"Noto Serif SC", "Songti SC", STSong, SimSun, serif', weight: 500, italic: false, outline: 0, shadow: 26, glow: 0, capsule: false },
  { id: "modern", name: "现代黑体", note: "干净克制", font: '"Noto Sans SC", "Microsoft YaHei", sans-serif', weight: 650, italic: false, outline: 0, shadow: 18, glow: 0, capsule: false },
  { id: "poster", name: "海报粗体", note: "强节拍冲击", font: 'Impact, "Arial Black", "Microsoft YaHei", sans-serif', weight: 900, italic: false, outline: 2, shadow: 8, glow: 0, capsule: false },
  { id: "editorial", name: "杂志衬线", note: "留白与呼吸", font: 'Didot, Bodoni MT, Georgia, "Noto Serif SC", serif', weight: 500, italic: true, outline: 0, shadow: 14, glow: 0, capsule: false },
  { id: "ink", name: "水墨楷体", note: "东方诗意", font: 'KaiTi, STKaiti, "Noto Serif SC", serif', weight: 500, italic: false, outline: 0, shadow: 22, glow: 0, capsule: false },
  { id: "mono", name: "等宽字幕", note: "冷感电子", font: '"JetBrains Mono", Consolas, "Microsoft YaHei", monospace', weight: 600, italic: false, outline: 0, shadow: 12, glow: 0, capsule: false },
  { id: "outline", name: "空心描边", note: "高对比舞台", font: '"Arial Black", "Microsoft YaHei", sans-serif', weight: 900, italic: false, outline: 3, shadow: 0, glow: 0, capsule: false },
  { id: "neon", name: "霓虹辉光", note: "夜景氛围", font: '"Noto Sans SC", "Microsoft YaHei", sans-serif', weight: 750, italic: false, outline: 0, shadow: 8, glow: 24, capsule: false },
  { id: "glass", name: "玻璃胶囊", note: "清晰信息层", font: '"Noto Sans SC", "Microsoft YaHei", sans-serif', weight: 650, italic: false, outline: 0, shadow: 18, glow: 0, capsule: true },
] as const;

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

export default function Home() {
  const [template, setTemplate] = useState<(typeof templates)[number]["id"]>("film");
  const [ratio, setRatio] = useState<Ratio>("16:9");
  const [background, setBackground] = useState<{ kind: BackgroundKind; url?: string }>({ kind: "gradient" });
  const [lyrics, setLyrics] = useState(sampleLyrics);
  const [activeLine, setActiveLine] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [dim, setDim] = useState(38);
  const [motion, setMotion] = useState(12);
  const [audioName, setAudioName] = useState("等待载入歌曲");
  const [subtitleStyle, setSubtitleStyle] = useState<(typeof subtitleStyles)[number]["id"]>("elegant");
  const [fontSize, setFontSize] = useState(56);
  const [letterSpacing, setLetterSpacing] = useState(8);
  const [subtitleY, setSubtitleY] = useState(52);
  const [subtitleAlign, setSubtitleAlign] = useState<SubtitleAlign>("center");
  const [textColor, setTextColor] = useState("#fffaf1");
  const [accentColor, setAccentColor] = useState("#c8ff3d");
  const ownedUrl = useRef<string | null>(null);

  const chosen = templates.find((item) => item.id === template) ?? templates[0];
  const chosenSubtitle = subtitleStyles.find((item) => item.id === subtitleStyle) ?? subtitleStyles[0];
  const ratioClass = ratio.replace(":", "-");
  const progress = activeLine === 0 ? 18 : activeLine === 1 ? 44 : 73;

  useEffect(() => () => {
    if (ownedUrl.current) URL.revokeObjectURL(ownedUrl.current);
  }, []);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => setActiveLine((line) => (line + 1) % lyrics.length), 2200);
    return () => window.clearInterval(timer);
  }, [playing, lyrics.length]);

  const backgroundStyle = useMemo(() => {
    if (background.kind === "image" && background.url) return { backgroundImage: `url(${background.url})` };
    return { backgroundImage: `radial-gradient(circle at 24% 20%, ${chosen.colors[1]}55, transparent 34%), linear-gradient(145deg, ${chosen.colors[0]}, #07080d 72%)` };
  }, [background, chosen]);

  function chooseBackground(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (ownedUrl.current) URL.revokeObjectURL(ownedUrl.current);
    const url = URL.createObjectURL(file);
    ownedUrl.current = url;
    setBackground({ kind: file.type.startsWith("video/") ? "video" : "image", url });
  }

  function chooseLyrics(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const lines = String(reader.result ?? "")
        .split(/\r?\n/)
        .map((line) => line.replace(/^\[[^\]]+\]/, "").trim())
        .filter(Boolean)
        .slice(0, 12);
      if (lines.length) {
        setLyrics(lines);
        setActiveLine(0);
      }
    };
    reader.readAsText(file);
  }

  return (
    <main className="studio-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="AutoMV Studio home"><span className="brand-mark">A</span><span>AutoMV <b>Studio</b></span></a>
        <div className="project-title"><span className="status-dot" />未命名歌词 MV <span className="saved">已自动保存</span></div>
        <div className="top-actions"><button className="ghost-button">帮助</button><button className="export-button"><Icon name="download" /> 导出 MV</button></div>
      </header>

      <section className="workspace">
        <aside className="panel left-panel">
          <div className="panel-heading"><div><span className="eyebrow">STYLE LAB</span><h2>视觉模板</h2></div><button className="icon-button"><Icon name="spark" /></button></div>
          <div className="template-grid">
            {templates.map((item) => (
              <button key={item.id} className={`template-card ${template === item.id ? "selected" : ""}`} onClick={() => setTemplate(item.id)}>
                <span className="template-swatch" style={{ background: `linear-gradient(135deg, ${item.colors[0]}, ${item.colors[1]})` }}><i>字</i></span>
                <span><b>{item.name}</b><small>{item.subtitle}</small></span>
              </button>
            ))}
          </div>

          <div className="divider" />
          <div className="section-title"><span><Icon name="upload" /> 素材</span><small>本地处理，不上传</small></div>
          <label className="upload-row"><span className="file-kind audio">♪</span><span><b>歌曲音频</b><small>{audioName}</small></span><input type="file" accept="audio/mp3,audio/wav,audio/*" onChange={(event) => setAudioName(event.target.files?.[0]?.name ?? "等待载入歌曲")} /><em>选择</em></label>
          <label className="upload-row"><span className="file-kind">L</span><span><b>LRC 歌词</b><small>{lyrics === sampleLyrics ? "使用示例歌词" : `${lyrics.length} 行已载入`}</small></span><input type="file" accept=".lrc,text/plain" onChange={chooseLyrics} /><em>选择</em></label>
          <label className="upload-row"><span className="file-kind image">▧</span><span><b>背景素材</b><small>图片或循环视频</small></span><input type="file" accept="image/*,video/*" onChange={chooseBackground} /><em>选择</em></label>

          <div className="divider" />
          <div className="section-title"><span><Icon name="layers" /> 画布</span></div>
          <div className="segmented">{(["16:9", "9:16", "1:1"] as Ratio[]).map((item) => <button key={item} onClick={() => setRatio(item)} className={ratio === item ? "active" : ""}>{item}</button>)}</div>
        </aside>

        <section className="stage-area">
          <div className="stage-toolbar"><span className="live-pill"><i /> 实时预览</span><span>{ratio} · 1080P</span><button>适应画布</button></div>
          <div className={`canvas-wrap ratio-${ratioClass}`}>
            <div className={`mv-canvas preset-${template} subtitle-${subtitleStyle}`} style={{ "--dim": dim / 100, "--motion": `${motion / 10}s`, "--subtitle-size": `${fontSize}px`, "--subtitle-tracking": `${letterSpacing / 100}em`, "--subtitle-y": `${subtitleY}%`, "--subtitle-color": textColor, "--subtitle-accent": accentColor, "--subtitle-outline": `${chosenSubtitle.outline}px`, "--subtitle-shadow": `${chosenSubtitle.shadow}px`, "--subtitle-glow": `${chosenSubtitle.glow}px`, "--subtitle-font": chosenSubtitle.font, "--subtitle-weight": chosenSubtitle.weight, "--subtitle-style": chosenSubtitle.italic ? "italic" : "normal", "--subtitle-align": subtitleAlign, "--subtitle-flex": subtitleAlign === "left" ? "flex-start" : subtitleAlign === "right" ? "flex-end" : "center" } as React.CSSProperties}>
              {background.kind === "video" && background.url ? <video className="background-media" src={background.url} autoPlay muted loop playsInline /> : <div className="background-media generated" style={backgroundStyle} />}
              <div className="background-grade" />
              <div className="film-grain" />
              <div className={`lyric-stage ${chosenSubtitle.capsule ? "with-capsule" : ""}`}>
                <span className="lyric-kicker">AUTOMV · {chosen.name}</span>
                {lyrics.slice(Math.max(0, activeLine - 1), activeLine + 2).map((line, index) => {
                  const sourceIndex = Math.max(0, activeLine - 1) + index;
                  return <p key={`${sourceIndex}-${line}`} className={sourceIndex === activeLine ? "current" : "context"}>{line}</p>;
                })}
                <span className="lyric-rule" />
              </div>
              <span className="timecode">00:{String(activeLine * 7 + 12).padStart(2, "0")}</span>
            </div>
          </div>
          <div className="transport">
            <button className="play-button" onClick={() => setPlaying((value) => !value)}><Icon name="play" /></button>
            <span>00:{String(activeLine * 7 + 12).padStart(2, "0")}</span><div className="timeline"><i style={{ width: `${progress}%` }} /><b style={{ left: `${progress}%` }} /></div><span>03:42</span><button className="sound-button">⌁</button>
          </div>
        </section>

        <aside className="panel right-panel">
          <div className="panel-heading"><div><span className="eyebrow">INSPECTOR</span><h2>画面调节</h2></div><span className="auto-badge">AUTO</span></div>
          <Control label="背景压暗" value={dim} min={0} max={80} suffix="%" onChange={setDim} />
          <Control label="缓慢运动" value={motion} min={0} max={30} suffix="" onChange={setMotion} />
          <div className="switch-row"><span><b>渐变遮罩</b><small>保证歌词可读性</small></span><button className="switch on"><i /></button></div>
          <div className="switch-row"><span><b>电影颗粒</b><small>轻微纹理层</small></span><button className="switch on"><i /></button></div>
          <div className="divider" />
          <div className="section-title"><span>字幕设计</span><small>9 种样式</small></div>
          <div className="subtitle-style-grid">
            {subtitleStyles.map((style) => <button key={style.id} title={style.note} className={subtitleStyle === style.id ? "selected" : ""} onClick={() => setSubtitleStyle(style.id)} style={{ fontFamily: style.font, fontStyle: style.italic ? "italic" : "normal", fontWeight: style.weight }}><b>Aa 字</b><small>{style.name}</small></button>)}
          </div>
          <div className="style-summary"><div className={`font-preview subtitle-${subtitleStyle}`}>Aa</div><span><b>{chosenSubtitle.name}</b><small>{chosenSubtitle.note} · {fontSize} px</small></span></div>
          <Control label="字号" value={fontSize} min={28} max={88} suffix=" px" onChange={setFontSize} />
          <Control label="字间距" value={letterSpacing} min={-4} max={28} suffix="%" onChange={setLetterSpacing} />
          <Control label="纵向位置" value={subtitleY} min={24} max={78} suffix="%" onChange={setSubtitleY} />
          <div className="compact-row"><span>对齐</span><div className="align-buttons">{(["left", "center", "right"] as SubtitleAlign[]).map((align) => <button key={align} className={subtitleAlign === align ? "active" : ""} style={{ textAlign: align }} onClick={() => setSubtitleAlign(align)} aria-label={`字幕${align === "left" ? "左" : align === "right" ? "右" : "居中"}对齐`}>≡</button>)}</div></div>
          <div className="color-row"><label><span>文字</span><input type="color" value={textColor} onChange={(event) => setTextColor(event.target.value)} /></label><label><span>强调色</span><input type="color" value={accentColor} onChange={(event) => setAccentColor(event.target.value)} /></label></div>
          <div className="divider" />
          <div className="layer-stack"><span className="section-title">合成层级</span>{["04  字幕与动效", "03  可读性遮罩", "02  色彩与颗粒", "01  背景图片 / 视频"].map((line) => <div key={line}><i />{line}</div>)}</div>
          <div className="render-note"><Icon name="spark" /><p><b>网页负责所见即所得预览</b><span>最终视频交给 FFmpeg + ASS 精确渲染，字体、描边和音频时间不会漂移。</span></p></div>
        </aside>
      </section>
    </main>
  );
}

function Control({ label, value, min, max, suffix, onChange }: { label: string; value: number; min: number; max: number; suffix: string; onChange: (value: number) => void }) {
  return <label className="control"><span><b>{label}</b><output>{value}{suffix}</output></span><input type="range" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} /></label>;
}
