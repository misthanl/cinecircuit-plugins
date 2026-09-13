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

test("Auto Signin keeps statistics without registering a main menu page", async () => {
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
          history: [
            { status: "signed", updated_at: new Date().toISOString(), payload: { site_id: "site-a", site_name: "站点 A", mode: "login" }, result: { ok: true, message: "登录正常" } },
            { status: "failed", updated_at: new Date().toISOString(), payload: { site_id: "site-a", site_name: "站点 A", mode: "sign" }, result: { ok: false, message: "连接超时" } },
          ],
        };
      }
      return {};
    },
    registerPage: (value) => { registration = value; },
    registerContribution: (value) => { contribution = value; },
  });

  assert.equal(registration, undefined);
  assert.deepEqual(
    { pluginId: contribution.pluginId, slot: contribution.slot, key: contribution.key },
    { pluginId: "auto-signin", slot: "plugin.statistics", key: "site-results" },
  );
  const statistics = mount(contribution.component, { props: { context: { close() {}, configure() {} } } });
  await flushPromises();
  assert.match(statistics.text(), /站点签到助手 · 数据统计/);
  assert.doesNotMatch(statistics.text(), /快速定位今日异常/);
  assert.match(statistics.text(), /今日登录1\/1/);
  assert.match(statistics.text(), /待处理异常1/);
  assert.match(statistics.text(), /签到失败，需要重试/);
  assert.match(statistics.text(), /站点 A/);
  assert.match(statistics.text(), /1 条签到记录/);
  assert.ok(statistics.findAll("button").some((button) => button.text() === "刷新"));
  assert.doesNotMatch(statistics.text(), /调整设置/);
  statistics.unmount();
});
