# AutoMV Studio

参考专业 PV 工具交互方式实现的纯歌词 MV 设计界面。它负责本地素材预览、画幅切换、背景调节、字幕样式设计和项目配置导出；最终视频由仓库根目录的 FFmpeg 管线渲染。

## 本地启动

需要 Node.js 22.13 或更高版本。

```powershell
pnpm install
pnpm dev
```

访问 `http://localhost:3000`。

## 检查

```powershell
pnpm lint
pnpm build
```

网页不会把音频、LRC 或背景素材上传到服务器。点击“导出配置”会下载 `automv-project.json`，之后在仓库根目录运行 `python render_project.py` 生成成片。
