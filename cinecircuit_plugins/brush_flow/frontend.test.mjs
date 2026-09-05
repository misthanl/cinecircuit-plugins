import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { test } from "node:test";
import { installSelectStub } from '../../tests/select-stub.mjs';

const require = createRequire(resolve("package.json"));
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>");
for (const key of ["window", "document", "Element", "HTMLElement", "SVGElement", "Node"]) globalThis[key] = dom.window[key];
const vue = require("vue");
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__ = vue;
const { install } = await import("../../.build/cinecircuit_plugins/brush_flow/frontend.js");
const { mount, flushPromises } = require("@vue/test-utils");
installSelectStub(vue,require('@vue/test-utils').config);

function setup(request) {
  let registration;
  install({ vue, request, registerPage: value => { registration = value; } });
  assert.equal(registration.pluginId, "brush-flow");
  return mount(registration.component);
}

test("brush flow preserves inventory, preview and save requests", async () => {
  const calls = [];
  const task = {
    id: "task-1", name: "保种", enabled: true, site_id: "site-1", downloader_id: "downloader-1",
    include: "WEB-DL", exclude: "CAM", min_size: 1, max_size: 20, max_add: 3,
    save_path: "/media", delete_ratio: 2, delete_seed_hours: 48, delete_task: false,
  };
  const request = async (path, init) => {
    calls.push({ path, init });
    if (path.endsWith("/api/inventory")) return {
      sites: [{ id: "site-1", name: "站点一" }],
      downloaders: [{ id: "downloader-1", name: "下载器一" }],
      config: { enabled: true }, tasks: [task],
    };
    if (path.endsWith("/api/preview")) return { count: 1, items: [{ title: "候选资源" }] };
    return {};
  };
  const wrapper = setup(request);
  await flushPromises();
  assert.match(wrapper.text(), /站点一/);

  await wrapper.findAll("button").find(button => button.text() === "预览选种").trigger("click");
  await flushPromises();
  assert.match(wrapper.text(), /候选资源/);
  assert.equal(calls.at(-1).path, "/plugins/brush-flow/api/preview");
  assert.equal(JSON.parse(calls.at(-1).init.body).task_id, "task-1");

  await wrapper.findAll("button").find(button => button.text() === "保存全部").trigger("click");
  await flushPromises();
  assert.equal(calls.at(-1).path, "/plugins/brush-flow");
  assert.equal(calls.at(-1).init.method, "PATCH");
  assert.deepEqual(JSON.parse(calls.at(-1).init.body).config.tasks, [task]);
  wrapper.unmount();
});
