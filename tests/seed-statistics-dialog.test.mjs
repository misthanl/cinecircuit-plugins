import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>");
for (const key of ["window", "document", "Element", "HTMLElement", "SVGElement", "Node"]) globalThis[key] = dom.window[key];
const vue = require("vue");
const { mount, flushPromises } = require("@vue/test-utils");
globalThis.__SEED_DIALOG_TEST_VUE__ = vue;
const { build } = await import("vite");
const { default: vuePlugin } = await import("@vitejs/plugin-vue");

const Container = vue.defineComponent({ setup: (_, { slots }) => () => vue.h("div", slots.default?.()) });
const Dialog = vue.defineComponent({
  props: ["modelValue", "maxWidth"], emits: ["update:modelValue"],
  setup: (_, { slots }) => () => vue.h("div", { role: "dialog" }, slots.default?.()),
});
const Button = vue.defineComponent({
  inheritAttrs: false, props: ["loading", "disabled"],
  setup: (props, { attrs, slots }) => () => vue.h("button", { ...attrs, disabled: props.disabled || props.loading }, slots.default?.()),
});
const Table = vue.defineComponent({
  props: ["items", "noDataText"],
  setup: props => () => vue.h("div", props.items.length ? props.items.map(item => `${item.name} ${item.statusLabel}`).join(" ") : props.noDataText),
});
const Fields = vue.defineComponent({ props: ["fields"], setup: props => () => vue.h("div", props.fields.map(field => field.label).join(" ")) });
const TextInput = vue.defineComponent({
  props: ["modelValue", "label"], emits: ["update:modelValue"],
  setup: (props, { attrs, emit }) => () => vue.h("input", { ...attrs, "aria-label": props.label, value: props.modelValue, onInput: event => emit("update:modelValue", event.target.value) }),
});
const Textarea = vue.defineComponent({
  props: ["modelValue", "label", "rows", "autoGrow", "noResize", "rules"], emits: ["update:modelValue"],
  setup: (props, { emit }) => () => vue.h("textarea", { "aria-label": props.label, rows: props.rows, value: props.modelValue, onInput: event => emit("update:modelValue", event.target.value) }),
});

for (const [folder, pluginId, name] of [["iyuu_autoseed", "iyuu-autoseed", "IYUU 辅种"], ["torrent_transfer", "torrent-transfer", "转移做种"]]) {
  test(`${pluginId}: statistics use a closable dialog and refresh after checking`, async () => {
    // Build in memory so verification cannot overwrite another task's .build output.
    const bundle = await build({
      configFile: false, logLevel: "silent",
      plugins: [{
        name: "seed-dialog-test-runtime", enforce: "pre",
        resolveId: id => id === "vue" ? "\0seed-test-vue" : null,
        load: id => id === "\0seed-test-vue" ? Object.keys(vue).filter(key => /^[A-Za-z_$][\w$]*$/.test(key)).map(key => `export const ${key} = globalThis.__SEED_DIALOG_TEST_VUE__.${key};`).join("\n") : null,
      }, vuePlugin()],
      build: { write: false, minify: false, lib: { entry: `cinecircuit_plugins/${folder}/frontend.ts`, formats: ["es"] } },
    });
    const code = (Array.isArray(bundle) ? bundle[0] : bundle).output.find(item => item.type === "chunk" && item.isEntry).code;
    const { install } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
    let registration, editor, closed = 0, refreshed = false, fail = false;
    const calls = [];
    install({ vue, ui: { components: { Card: Container, Button, Alert: Container, Dialog, SchemaFields: Fields } },
      registerEditor: value => { editor = value; },
      registerContribution: value => { registration = value; },
      request: async (path, options) => {
        calls.push([path, options?.method || "GET"]);
        if (path.endsWith("/config/secret/token")) return { value: "saved-iyuu-value" };
        if (fail) throw new Error("连接失败");
        if (options?.method === "POST") { refreshed = true; return {}; }
        return { counts: refreshed ? { seeding: 3 } : {}, items: refreshed ? [{ id: "1", name: "测试种子", status: "seeding", timestamp: 0 }] : [] };
      },
    });
    const wrapper = mount(registration.component, { props: { context: { installation: { name }, close: () => { closed++; } } }, global: { components: { VDataTable: Table, VIcon: Container } } });
    await flushPromises();
    assert.equal(wrapper.find('[role="dialog"]').exists(), true);
    assert.equal(wrapper.find("h2").text(), `${name} · 数据统计`);
    assert.equal(wrapper.findAll(".seed-statistics-metrics > div").length, 4);
    assert.match(wrapper.text(), /暂无任务记录/);
    const button = label => wrapper.findAll("button").find(item => item.text() === label);
    await button("检查校验").trigger("click");
    await flushPromises();
    assert.deepEqual(calls.slice(-2), [[`/plugins/${pluginId}/api/check`, "POST"], [`/plugins/${pluginId}/api/statistics`, "GET"]]);
    assert.equal(wrapper.find("dd").text(), "3");
    assert.match(wrapper.text(), /测试种子 做种中/);
    fail = true;
    await button("刷新").trigger("click");
    await flushPromises();
    assert.match(wrapper.find('[role="alert"]').text(), /连接失败/);
    assert.match(wrapper.text(), /测试种子/);
    await wrapper.find('[aria-label="关闭"]').trigger("click");
    assert.equal(closed, 1);
    wrapper.findComponent(Dialog).vm.$emit("update:modelValue", false);
    assert.equal(closed, 2);
    wrapper.unmount();
    if (pluginId === "iyuu-autoseed") {
      const model = vue.ref({ token: "", token_configured: true, nopaths: "" });
      const Parent = vue.defineComponent({ setup: () => () => vue.h(editor.component, {
        modelValue: model.value, "onUpdate:modelValue": value => { model.value = value; },
        fields: [
          { key: "enabled", label: "启用自动辅种" },
          { key: "onlyonce", label: "立即执行一次" },
          { key: "token", label: "IYUU Token", secret: true },
          { key: "nopaths", label: "不辅种数据目录" },
        ],
      }) });
      const config = mount(Parent, { global: { components: { VTextField: TextInput, VTextarea: Textarea } } });
      await flushPromises();
      const token = config.find('[aria-label="IYUU Token"]');
      assert.equal(token.attributes("type"), "text");
      assert.equal(token.attributes("autocomplete"), "off");
      assert.equal(token.element.value, "saved-iyuu-value");
      assert.equal(config.find('input[type="password"]').exists(), false);
      assert.doesNotMatch(config.text(), /立即执行一次|清除已保存/);
      assert.equal(config.find("textarea").attributes("rows"), "1");
      assert.equal(config.findComponent(Textarea).props("autoGrow"), false);
      assert.equal(config.findComponent(Textarea).props("noResize"), false);
      await token.setValue("replacement-value");
      assert.equal(model.value.token, "replacement-value");
      assert.equal(model.value.token_clear, false);
      await token.setValue("");
      assert.equal(model.value.token_clear, true);
      config.unmount();
    } else {
      const model = vue.ref({ frompath: "/source\n/source/tv", topath: "/target\n/tv", path_mappings: "" });
      const Parent = vue.defineComponent({ setup: () => () => vue.h(editor.component, {
        modelValue: model.value, "onUpdate:modelValue": value => { model.value = value; },
        fields: [
          { key: "path_mappings", label: "保存目录映射", input_type: "textarea", placeholder: "每行一组：源目录#目标目录；留空沿用原路径。" },
          { key: "frompath", label: "源保存目录映射", input_type: "textarea", visible: false },
          { key: "topath", label: "目标保存目录映射", input_type: "textarea", visible: false },
        ],
      }) });
      const config = mount(Parent, { global: { components: { VTextarea: Textarea } } });
      const textarea = config.find("textarea");
      assert.equal(config.findAll("textarea").length, 1);
      assert.equal(textarea.element.value, "/source#/target\n/source/tv#/tv");
      assert.equal(textarea.attributes("rows"), "1");
      const rule = config.findComponent(Textarea).props("rules")[0];
      assert.equal(rule("/source#/target\n/source/tv#/tv"), true);
      assert.notEqual(rule("/source#"), true);
      await textarea.setValue("/data#/media");
      assert.equal(model.value.path_mappings, "/data#/media");
      assert.equal(model.value.frompath, "");
      assert.equal(model.value.topath, "");
      await textarea.setValue("");
      assert.equal(textarea.element.value, "");
      assert.equal(model.value.path_mappings, "");
      config.unmount();
    }
  });
}
