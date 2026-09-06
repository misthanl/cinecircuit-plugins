import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";
const require = createRequire(resolve("package.json"));
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>");
for (const key of ["window", "document", "Element", "HTMLElement", "SVGElement", "Node"]) globalThis[key] = dom.window[key];
const vue = require("vue");
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__ = vue;
const { install } = await import("../../.build/cinecircuit_plugins/auto_signin/frontend.js");
const { mount, flushPromises } = require("@vue/test-utils");

test("Auto Signin loads sites, saves selections and registers its page", async () => {
  const requests = [];
  let registration;
  let contribution;
  const Box = vue.defineComponent({ inheritAttrs: false, setup(_, { attrs, slots }) { return () => vue.h("div", attrs, slots.default?.()); } });
  const Button = vue.defineComponent({ inheritAttrs: false, setup(_, { attrs, slots }) { return () => vue.h("button", attrs, slots.default?.()); } });
  install({
    vue,
    ui: { components: { Alert: Box, Button, Card: Box, Dialog: Box } },
    request: async (path, init) => {
      requests.push({ path, init });
      if (path.endsWith("/api/inventory")) {
        return {
          items: [{ id: "site-a", name: "站点 A", enabled: true }],
          config: { notification_enabled: true },
          selected: { sign_sites: [], login_sites: ["site-a"] },
          history: [{ status: "signed", payload: { site_id: "site-a", mode: "login" }, result: { ok: true, message: "登录正常" } }],
        };
      }
      return {};
    },
    registerPage: (value) => { registration = value; },
    registerContribution: (value) => { contribution = value; },
  });

  assert.deepEqual(
    { pluginId: registration.pluginId, route: registration.route, title: registration.title },
    { pluginId: "auto-signin", route: "plugin-auto-signin", title: "自动签到" },
  );
  assert.deepEqual(
    { pluginId: contribution.pluginId, slot: contribution.slot, key: contribution.key },
    { pluginId: "auto-signin", slot: "plugin.statistics", key: "site-results" },
  );
  const wrapper = mount(registration.component);
  await flushPromises();
  assert.match(wrapper.text(), /站点 A/);
  const checkboxes = wrapper.findAll('input[type="checkbox"]');
  assert.equal(checkboxes.length, 2);
  assert.equal(checkboxes[0].element.checked, true);
  checkboxes[1].element.checked = true;
  await checkboxes[1].trigger("change");
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
  assert.match(wrapper.text(), /最近成功1/);
  assert.match(wrapper.text(), /登录正常/);
  assert.match(wrapper.text(), /检查登录/);
  assert.match(wrapper.text(), /测试签到/);
  wrapper.unmount();

  const statistics = mount(contribution.component, { props: { context: { close() {}, configure() {} } } });
  await flushPromises();
  assert.match(statistics.text(), /站点签到与登录统计/);
  assert.match(statistics.text(), /保持登录站点1/);
  assert.match(statistics.text(), /站点 A/);
  assert.match(statistics.text(), /登录正常/);
  statistics.unmount();
});
