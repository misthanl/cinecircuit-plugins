import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";

// Test dependencies come from the working directory, never from the plugin bundle.
const require = createRequire(resolve("package.json"));
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>");
for (const key of ["window", "document", "Element", "HTMLElement", "SVGElement", "Node"]) globalThis[key] = dom.window[key];
const vue = require("vue");
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__ = vue;
const { install } = await import("../../.build/cinecircuit_plugins/cookiecloud/frontend.js");
const { mount, flushPromises } = require("@vue/test-utils");
const Box = { setup: (_, { slots }) => () => vue.h("div", slots.default?.()) };
const Button = { props: ["disabled", "loading"], emits: ["click"], setup: (props, { slots, emit }) => () => vue.h("button", { disabled: props.disabled || props.loading, onClick: () => emit("click") }, slots.default?.()) };
const Control = vue.defineComponent({ name: "CookieCloudControlStub", props: ["modelValue", "type", "disabled", "label", "appendInnerIcon", "items", "hint"], emits: ["update:modelValue", "click:append-inner"], render: () => vue.h("span") });
function setup(request) {
  const contributions = [], editors = [];
  install({ vue, request, ui: { components: { Button, Card: Box, Dialog: Box, Chip: Box, Alert: Box } }, registerContribution: value => contributions.push(value), registerEditor: value => editors.push(value) });
  return { contributions, editors };
}
const global = { stubs: { VIcon: true, VSwitch: Control, VTextField: Control, VSelect: Control } };

test("CookieCloud owns its log-free statistics and retries failed requests", async () => {
  let calls = 0;
  const { contributions } = setup(async path => {
    assert.equal(path, "/plugins/cookiecloud/runs?limit=100");
    if (++calls === 1) throw new Error("读取失败");
    return { items: [{ status: "completed" }, { status: "completed", display_status: "skipped" }, { status: "completed" }] };
  });
  assert.equal(contributions[0].slot, "plugin.statistics");
  let closed = false;
  const wrapper = mount(contributions[0].component, { props: { context: { installation: { enabled: true, next_run_at: "2026-09-04T08:10:49Z" }, close: () => { closed = true; } } }, global });
  await flushPromises();
  assert.match(wrapper.text(), /读取失败/);
  await wrapper.findAll("button").find(button => button.text() === "刷新").trigger("click");
  await flushPromises();
  assert.deepEqual(wrapper.findAll(".cookie-metrics dd").map(item => item.text()), ["3次", "2次", "0次", "0次"]);
  assert.match(wrapper.get(".cookie-results__legend").text(), /已跳过1/);
  assert.equal(wrapper.find("table").exists(), false);
  await wrapper.get('[aria-label="关闭"]').trigger("click");
  assert.equal(closed, true);
  wrapper.unmount();
});

test("CookieCloud's unified editor reveals the password and uses the compact row layout", async () => {
  const { editors } = setup(async () => ({}));
  assert.deepEqual(editors.map(editor => editor.key), ["cookiecloud", "cookiecloud:connection"]);
  const modelValue = { enabled: true, user_key: "key", password: "saved-password", run_once: false, notification_enabled: false, cron: "" };
  const wrapper = mount(editors[0].component, { props: { modelValue }, global });
  const controls = wrapper.findAllComponents({ name: "CookieCloudControlStub" });
  assert.deepEqual(controls.map(control => control.props("label")), ["启用站点 Cookie 同步", "保存后立即运行一次", "用户 KEY", "端对端加密密码", "定时检查周期", "发送通知"]);
  assert.deepEqual(controls.map(control => control.props("hint")), [undefined, undefined, undefined, undefined, undefined, undefined]);
  assert.equal(wrapper.text().includes("清除已保存的端对端加密密码"), false);
  assert.equal(wrapper.text().includes("检查计划"), false);
  assert.equal(controls[3].props("type"), "password");
  controls[3].vm.$emit("click:append-inner");
  await flushPromises();
  assert.equal(controls[3].props("type"), "text");
  assert.equal(wrapper.emitted("update:modelValue"), undefined);
  controls[1].vm.$emit("update:modelValue", true);
  assert.deepEqual(wrapper.emitted("update:modelValue")[0][0], { ...modelValue, run_once: true });
  wrapper.unmount();
  const reopened = mount(editors[0].component, { props: { modelValue }, global });
  assert.equal(reopened.findAllComponents({ name: "CookieCloudControlStub" })[3].props("type"), "password");
  reopened.unmount();
});

test("CookieCloud's unified editor restores the KEY and shows a masked saved password", async () => {
  const requests = [];
  const { editors } = setup(async path => {
    requests.push(path);
    return { value: path.endsWith("user_key") ? "restored-key" : "restored-password" };
  });
  const modelValue = { enabled: true, user_key: "", password: "", cron: "" };
  const wrapper = mount(editors[0].component, { props: { modelValue }, global });
  await flushPromises();
  const controls = wrapper.findAllComponents({ name: "CookieCloudControlStub" });
  assert.deepEqual(requests, [
    "/plugins/cookiecloud/config/secret/user_key",
    "/plugins/cookiecloud/config/secret/password",
  ]);
  assert.equal(controls[2].props("modelValue"), "restored-key");
  assert.equal(controls[3].props("modelValue"), "restored-password");
  assert.equal(controls[3].props("type"), "password");
  controls[3].vm.$emit("click:append-inner");
  await flushPromises();
  assert.equal(controls[3].props("type"), "text");
  assert.equal(requests.length, 2);
  wrapper.unmount();
});
