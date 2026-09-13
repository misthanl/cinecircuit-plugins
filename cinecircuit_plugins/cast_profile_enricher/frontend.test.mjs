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
const { install } = await import("../../.build/cinecircuit_plugins/cast_profile_enricher/frontend.js");
const { mount, flushPromises } = require("@vue/test-utils");

test("cast profile settings use one compact editor with server selection", async () => {
  let editor;
  const requests = [];
  const Field = vue.defineComponent({
    inheritAttrs: false,
    props: { label: String, field: Object, modelValue: null },
    setup(props, { slots }) { return () => vue.h("div", [props.label || props.field?.label, slots.default?.()]); },
  });
  install({
    vue,
    request: async (path) => {
      requests.push(path);
      return { items: [{ id: "emby-1", label: "Emby 1" }] };
    },
    ui: { components: { CronField: Field } },
    registerEditor: value => { editor = value; },
  });

  assert.deepEqual(
    { domain: editor.domain, key: editor.key },
    { domain: "plugin", key: "cast-profile-enricher" },
  );
  const wrapper = mount(editor.component, {
    props: { modelValue: { enabled: true, update_biography: true, update_images: true } },
    global: { components: { VSelect: Field, VSwitch: Field, VTextField: Field } },
  });
  await flushPromises();

  assert.equal(requests[0], "/plugins/cast-profile-enricher/sdk/resources/media_server?capability=read&capability=write_metadata&limit=100");
  assert.match(wrapper.text(), /启用定时生成/);
  assert.match(wrapper.text(), /触发事件/);
  assert.match(wrapper.text(), /触发后延迟执行/);
  assert.match(wrapper.text(), /执行周期/);
  assert.match(wrapper.text(), /媒体服务器/);
  assert.match(wrapper.text(), /处理范围/);
  assert.doesNotMatch(wrapper.text(), /资料优先级/);
  assert.match(wrapper.text(), /人物简介/);
  assert.doesNotMatch(wrapper.text(), /人物头像/);
  assert.doesNotMatch(wrapper.text(), /自动维护|写入策略|完善规则/);
  const fieldOrder = ["启用定时生成", "执行周期", "触发事件", "触发后延迟执行", "补充人物简介", "处理范围", "移除无法完善的人物", "媒体服务器"]
    .map(label => wrapper.text().indexOf(label));
  assert.ok(fieldOrder.every((position, index) => index === 0 || position > fieldOrder[index - 1]));
  const triggerField = wrapper.findAllComponents(Field)
    .find(component => component.props("label") === "触发事件");
  assert.equal(triggerField?.props("modelValue"), null);
  const removalField = wrapper.findAllComponents(Field)
    .find(component => component.props("label") === "移除无法完善的人物");
  assert.equal(removalField?.props("modelValue"), false);
  wrapper.unmount();
});

test("cast profile statistics presents only the latest processing summary", async () => {
  let contribution;
  const requests = [];
  const PassThrough = vue.defineComponent({
    inheritAttrs: false,
    setup(_, { slots }) { return () => vue.h("div", slots.default?.()); },
  });
  const Button = vue.defineComponent({
    inheritAttrs: false,
    emits: ["click"],
    setup(_, { attrs, emit, slots }) {
      return () => vue.h("button", { ...attrs, onClick: () => emit("click") }, slots.default?.());
    },
  });

  install({
    vue,
    request: async (path) => {
      requests.push(path);
      return {
        items: [{
          display_status: "completed",
          started_at: "2026-09-07T13:56:06Z",
          result: {
            scanned_media: 12,
            scanned_people: 86,
            updated_profiles: 24,
            updated_images: 18,
            updated_names: 12,
            updated_roles: 9,
            updated_biographies: 7,
            cache_hits: 22,
            failures: 2,
          },
        }],
      };
    },
    ui: { components: {
      Alert: PassThrough,
      Button,
      Card: PassThrough,
      Chip: PassThrough,
      CronField: PassThrough,
      Dialog: PassThrough,
    } },
    registerEditor: () => {},
    registerContribution: value => { contribution = value; },
  });

  assert.deepEqual(
    { pluginId: contribution.pluginId, slot: contribution.slot, key: contribution.key },
    { pluginId: "cast-profile-enricher", slot: "plugin.statistics", key: "overview" },
  );
  const wrapper = mount(contribution.component, {
    props: { context: { close() {}, installation: { enabled: true } } },
    global: { components: { VIcon: PassThrough } },
  });
  await flushPromises();

  assert.equal(requests[0], "/plugins/cast-profile-enricher/runs?limit=1");
  assert.match(wrapper.text(), /检查媒体/);
  assert.match(wrapper.text(), /检查人物/);
  assert.match(wrapper.text(), /更新资料/);
  assert.match(wrapper.text(), /更新图片/);
  assert.equal(wrapper.findAll(".cast-metrics > div").length, 8);
  assert.equal(wrapper.findAll(".cast-metric-icon").length, 0);
  assert.deepEqual(wrapper.findAll(".cast-metrics dt").map(item => item.text()), ["检查媒体", "检查人物", "更新资料", "更新图片", "中文姓名", "中文角色", "中文简介", "缓存命中"]);
  assert.deepEqual(wrapper.findAll(".cast-metrics dd").map(item => item.text()), ["12", "86", "24", "18", "12", "9", "7", "22"]);
  assert.ok(requests.includes("/plugins/cast-profile-enricher/api/progress"));
  assert.match(wrapper.text(), /检查 12 部媒体 · 86 位人物/);
  assert.match(wrapper.text(), /资料更新 24/);
  assert.match(wrapper.text(), /图片更新 18/);
  assert.match(wrapper.text(), /处理失败 2/);
  assert.doesNotMatch(wrapper.text(), /最近执行|执行明细/);
  assert.equal(wrapper.findAll("button").filter(item => item.text() === "刷新").length, 1);
  wrapper.unmount();
});
