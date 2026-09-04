import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { test } from "node:test";

const require = createRequire(resolve("package.json"));
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>");
for (const key of ["window", "document", "Element", "HTMLElement", "SVGElement", "Node"]) globalThis[key] = dom.window[key];
const vue = require("vue");
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__ = vue;
const { install } = await import("../../.build/cinecircuit_plugins/media_cover_generator/frontend.js");
const { mount, flushPromises } = require("@vue/test-utils");

function setup(request) {
  let registration;
  install({ vue, request, registerPage: value => { registration = value; } });
  assert.equal(registration.pluginId, "emby-cover-generator");
  return mount(registration.component);
}

test("cover generator preserves server selection, library toggles and run sequence", async () => {
  const calls = [];
  const request = async (path, init) => {
    calls.push({ path, init });
    if (path.endsWith("/api/inventory")) return {
      servers: [{ id: "server-1", name: "Emby" }], libraries: [],
      config: { cover_style_base: "single", selected_servers: [], include_libraries: [] },
    };
    if (path.includes("/api/libraries?")) return { items: [{ id: "library-1", name: "电影", collection_type: "movies" }] };
    return {};
  };
  const wrapper = setup(request);
  await flushPromises();
  await wrapper.get("select").setValue("server-1");
  await flushPromises();
  assert.equal(calls.at(-1).path, "/plugins/emby-cover-generator/api/libraries?server_id=server-1");

  await wrapper.get('input[type="checkbox"]').setValue(true);
  await wrapper.findAll("button").find(button => button.text() === "保存并生成").trigger("click");
  await flushPromises();

  const saveCall = calls.find(call => call.path === "/plugins/emby-cover-generator");
  assert.equal(saveCall.init.method, "PATCH");
  const saved = JSON.parse(saveCall.init.body).config;
  assert.deepEqual(saved.selected_servers, ["server-1"]);
  assert.deepEqual(saved.include_libraries, ["library-1"]);
  assert.equal(saved.dry_run, false);
  assert.equal(calls.at(-1).path, "/plugins/emby-cover-generator/run");
  assert.equal(calls.at(-1).init.method, "POST");
  wrapper.unmount();
});
