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
const { mount, flushPromises } = require("@vue/test-utils");
const { install } = await import("../../.build/cinecircuit_plugins/storage_recycle_cleaner/frontend.js");
const Text = { name: "SecretInput", props: ["modelValue", "type", "errorMessages"], emits: ["update:modelValue", "click:append-inner"], render: () => vue.h("input") };
const Fields = { name: "Fields", props: ["fields", "modelValue", "pluginId"], render: () => vue.h("div") };
function editor(request) {
  let component;
  install({ vue, request, ui: { components: { SchemaFields: Fields } }, registerContribution: () => {}, registerEditor: entry => { component = entry.component; } });
  return mount(component, { props: { modelValue: { storage_id: "", password: "" } },
    attrs: { fields: ["enabled", "cron", "storage_id", "password", "confirm_permanent", "notification_enabled"].map(key => ({ key, label: key })) },
    global: { stubs: { VTextField: Text } } });
}
test("recycle editor uses common fields, normalizes empty storage and restores a masked secret", async () => {
  const wrapper = editor(async path => { assert.equal(path, "/plugins/storage-recycle-cleaner/config/secret/password"); return { value: "123456" }; });
  await flushPromises();
  assert.equal(wrapper.findAllComponents(Fields).length, 5);
  assert.equal(wrapper.findAllComponents(Fields)[2].props("modelValue").storage_id, null);
  assert.equal(wrapper.findAllComponents(Fields)[2].props("pluginId"), "storage-recycle-cleaner");
  const input = wrapper.findComponent(Text);
  assert.equal(input.props("modelValue"), "123456");
  assert.equal(input.props("type"), "password");
  assert.equal(wrapper.emitted("update:modelValue"), undefined);
  input.vm.$emit("click:append-inner");
  await flushPromises();
  assert.equal(input.props("type"), "text");
  wrapper.unmount();
});
test("secret read failure stays masked and can be retried", async () => {
  let attempts = 0;
  const wrapper = editor(async () => { if (++attempts === 1) throw new Error("private"); return { value: "123456" }; });
  await flushPromises();
  const input = wrapper.findComponent(Text);
  assert.match(input.props("errorMessages"), /读取失败/);
  assert.doesNotMatch(input.props("errorMessages"), /private/);
  input.vm.$emit("click:append-inner");
  await flushPromises();
  assert.equal(input.props("type"), "text");
  assert.equal(input.props("errorMessages"), "");
  wrapper.unmount();
});
test("late secret response never replaces user edits", async () => {
  let finish;
  const wrapper = editor(() => new Promise(resolve => { finish = resolve; }));
  const input = wrapper.findComponent(Text);
  input.vm.$emit("update:modelValue", "654321");
  const update = wrapper.emitted("update:modelValue").at(-1)[0];
  assert.equal(update.password_clear, false);
  await wrapper.setProps({ modelValue: update });
  finish({ value: "123456" });
  await flushPromises();
  assert.equal(input.props("modelValue"), "654321");
  wrapper.unmount();
});

const Box = { setup: (_, { slots }) => () => vue.h("div", slots.default?.()) };
const Dialog = { props: ["maxWidth", "width"], setup: (_, { slots }) => () => vue.h("div", slots.default?.()) };
const Button = { props: ["loading"], emits: ["click"], setup: (props, { slots, emit }) => () => vue.h("button", { disabled: props.loading, onClick: () => emit("click") }, slots.default?.()) };
function statistics(request, configEnabled = true) {
  let component;
  install({ vue, request, ui: { components: { SchemaFields: Fields, Button, Card: Box, Dialog, Chip: Box, Alert: Box } }, registerEditor: () => {}, registerContribution: entry => { component = entry.component; } });
  return mount(component, { props: { context: { close() {}, installation: { enabled: true, config: { enabled: configEnabled }, next_run_at: "2026-09-09T03:00:00+08:00" } } }, global: { stubs: { VIcon: true } } });
}
test("statistics use CookieCloud width, four metrics and no execution table", async () => {
  const wrapper = statistics(async path => {
    assert.equal(path, "/plugins/storage-recycle-cleaner/runs?limit=100");
    return { items: [{ status: "completed" }, { status: "failed" }, { status: "running" }, { status: "completed", display_status: "skipped" }] };
  });
  await flushPromises();
  assert.equal(wrapper.findComponent(Dialog).props("maxWidth"), 780);
  assert.equal(wrapper.findComponent(Dialog).props("width"), "calc(100vw - 32px)");
  assert.deepEqual(wrapper.findAll("dd").map(item => item.text()), ["3次", "1次", "1次", "1次"]);
  assert.match(wrapper.text(), /定时清理已启用/);
  assert.doesNotMatch(wrapper.text(), /执行明细|最近一次|每页数量|插件正在运行/);
  assert.equal(wrapper.find("table").exists(), false);
  wrapper.unmount();
});
test("enabled plugin does not imply scheduling is enabled and empty counts are zero", async () => {
  const wrapper = statistics(async () => ({ items: [] }), false);
  await flushPromises();
  assert.match(wrapper.text(), /定时清理未启用/);
  assert.deepEqual(wrapper.findAll("dd").map(item => item.text()), ["0次", "0次", "0次", "0次"]);
  wrapper.unmount();
});
test("statistics read failure can retry without executing a cleanup", async () => {
  let calls = 0;
  const wrapper = statistics(async path => {
    assert.match(path, /\/runs\?limit=100$/);
    if (++calls === 1) throw new Error("private");
    return { items: [] };
  });
  await flushPromises();
  assert.match(wrapper.text(), /统计加载失败/);
  await wrapper.findAll("button").find(button => button.text() === "刷新").trigger("click");
  await flushPromises();
  assert.equal(calls, 2);
  assert.doesNotMatch(wrapper.text(), /统计加载失败/);
  wrapper.unmount();
});
