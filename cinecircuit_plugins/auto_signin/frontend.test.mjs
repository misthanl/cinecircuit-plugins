import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { install } from "../../.build/cinecircuit_plugins/auto_signin/frontend.js";

const require = createRequire(resolve("package.json"));
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>");
for (const key of ["window", "document", "Element", "HTMLElement", "SVGElement", "Node"]) globalThis[key] = dom.window[key];
const vue = require("vue");
const { mount, flushPromises } = require("@vue/test-utils");

test("Auto Signin loads sites, saves selections and registers its page", async () => {
  const requests = [];
  let registration;
  install({
    vue,
    request: async (path, init) => {
      requests.push({ path, init });
      if (path.endsWith("/api/inventory")) {
        return {
          items: [{ id: "site-a", name: "站点 A", enabled: true }],
          config: { notification_enabled: true },
          selected: { sign_sites: [], login_sites: ["site-a"] },
        };
      }
      return {};
    },
    registerPage: (value) => { registration = value; },
  });

  assert.deepEqual(
    { pluginId: registration.pluginId, route: registration.route, title: registration.title },
    { pluginId: "auto-signin", route: "plugin-auto-signin", title: "自动签到" },
  );
  const wrapper = mount(registration.component);
  await flushPromises();
  assert.match(wrapper.text(), /站点 A/);
  const checkboxes = wrapper.findAll('input[type="checkbox"]');
  assert.equal(checkboxes.length, 2);
  assert.equal(checkboxes[1].element.checked, true);
  checkboxes[0].element.checked = true;
  await checkboxes[0].trigger("change");
  await wrapper.findAll("button").find((button) => button.text() === "保存选择").trigger("click");
  await flushPromises();

  assert.equal(requests[0].path, "/plugins/auto-signin/api/inventory");
  assert.equal(requests[1].path, "/plugins/auto-signin");
  assert.equal(requests[1].init.method, "PATCH");
  assert.deepEqual(JSON.parse(requests[1].init.body).config, {
    notification_enabled: true,
    sign_sites: ["site-a"],
    login_sites: ["site-a"],
  });
  assert.match(wrapper.text(), /站点选择已保存/);
  wrapper.unmount();
});
