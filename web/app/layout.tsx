import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AutoMV Studio — 纯歌词 MV 编辑器",
  description: "从歌曲、LRC 与背景素材生成字体优雅的纯歌词 MV。",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
