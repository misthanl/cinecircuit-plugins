import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { install } from "../../.build/cinecircuit_plugins/subtitle_manager/frontend.js";

const require = createRequire(resolve("package.json"));
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>");
for (const key of ["window", "document", "Element", "HTMLElement", "SVGElement", "Node"]) globalThis[key] = dom.window[key];
const vue = require("vue");
const { mount, flushPromises } = require("@vue/test-utils");

test("Subtitle Manager loads the media catalog, searches online and registers its page", async () => {
  const paths = [];
  let registration;
  install({
    vue,
    request: async (path) => {
      paths.push(path);
      if (path.startsWith("/plugins/subtitle-manager/api/catalog?")) {
        return { items: [{ path: "D:/media/示例电影.mkv", title: "示例电影", subtitles: [{ name: "示例电影.zh.srt", size: 2048 }] }] };
      }
      if (path.startsWith("/plugins/subtitle-manager/api/online?")) {
        return { items: [{ title: "示例电影 中文字幕", provider: "OpenSubtitles", language: "zh-CN", url: "https://example.test/subtitle" }] };
      }
      throw new Error(`unexpected request: ${path}`);
    },
    registerPage: (value) => { registration = value; },
  });

  assert.deepEqual(
    { pluginId: registration.pluginId, route: registration.route, title: registration.title },
    { pluginId: "subtitle-manager", route: "plugin-subtitle-manager", title: "字幕大师" },
  );
  const wrapper = mount(registration.component);
  await flushPromises();
  assert.match(wrapper.text(), /示例电影/);
  assert.match(wrapper.text(), /示例电影\.zh\.srt/);
  assert.match(wrapper.text(), /已读取 1 个本地媒体文件/);

  await wrapper.findAll("button").find((button) => button.text() === "在线搜索字幕").trigger("click");
  await flushPromises();
  assert.deepEqual(paths, [
    "/plugins/subtitle-manager/api/catalog?query=&limit=100",
    "/plugins/subtitle-manager/api/online?query=%E7%A4%BA%E4%BE%8B%E7%94%B5%E5%BD%B1",
  ]);
  assert.match(wrapper.text(), /OpenSubtitles · zh-CN/);
  assert.match(wrapper.text(), /找到 1 条在线字幕/);
  assert.equal(wrapper.get('a[href="https://example.test/subtitle"]').attributes("target"), "_blank");
  wrapper.unmount();
});
