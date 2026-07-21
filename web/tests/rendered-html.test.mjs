import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const templateRoot = new URL("../", import.meta.url);

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the AutoMV Studio editor", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>AutoMV Studio — 纯歌词 MV 编辑器<\/title>/i);
  assert.match(html, /成片视觉方向/);
  assert.match(html, /逐句运动/);
  assert.match(html, /电影呼吸/);
  assert.match(html, /霓虹余响/);
  assert.match(html, /LRC 时间驱动/);
  assert.match(html, /导出配置/);
  assert.doesNotMatch(html, /Your site is taking shape/);
});

test("keeps preview and render motion configuration aligned", async () => {
  const [page, css, layout] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
  ]);

  for (const preset of [
    "cinematic",
    "float",
    "punch",
    "handwritten",
    "neon",
    "minimal",
  ]) {
    assert.match(page, new RegExp(`motion: "${preset}"|id: "${preset}"`));
    assert.match(css, new RegExp(`motion-${preset}`));
  }

  assert.match(page, /motionPreset/);
  assert.match(page, /displayMode/);
  assert.match(page, /offsetSeconds/);
  assert.match(page, /audioTime - lyricOffset/);
  assert.match(page, /等待歌曲开始/);
  assert.match(layout, /AutoMV Studio/);

  await assert.rejects(
    access(new URL("../app/_sites-preview/SkeletonPreview.tsx", import.meta.url)),
  );
  await assert.rejects(access(new URL("public/_sites-preview", templateRoot)));
});
