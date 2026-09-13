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
const Field = vue.defineComponent({ setup: () => () => vue.h("div") });


for (const [directory, editorKey, keys, delayKey] of [
  ["cast_profile_enricher", "cast-profile-enricher", ["enabled", "cron", "trigger_event", "scrape_delay", "update_biography", "condition", "remove_unresolved", "selected_servers"], "scrape_delay"],
  ["cookiecloud", "cookiecloud", ["enabled", "run_once", "cron", "notification_enabled"], null],
  ["media_cover_generator", "emby-cover-generator:run", ["enabled", "cron", "trigger_event", "delay", "dry_run", "max_libraries"], "delay"],
]) {
  test(`${editorKey} delegates manifest fields to the shared renderer`, async () => {
    const registrations = [];
    const calls = [];
    const Shared = vue.defineComponent({
      props: ["fields", "modelValue", "pluginId"],
      emits: ["update:modelValue"],
      setup(props, { emit }) {
        calls.push(props);
        return () => vue.h("button", { onClick: () => emit("update:modelValue", { ...props.modelValue, enabled: true }) }, "shared");
      },
    });
    const { install } = await import(`../.build/cinecircuit_plugins/${directory}/frontend.js`);
    install({ vue, request: async () => ({ items: [], servers: [], libraries: [] }),
      ui: { components: { SchemaFields: Shared, CronField: Field } },
      registerEditor: item => registrations.push(item), registerPage() {}, registerContribution() {},
    });
    const fields = keys.map(key => ({ key, label: `manifest:${key}`, default: false,
      validation: { minimum: 0, maximum: 3600 }, options: [{ label: "option", value: "value" }] }));
    const wrapper = mount(registrations.find(item => item.key === editorKey).component, {
      props: { fields, modelValue: { trigger_event: "", user_key: "fixture", password: "fixture" } },
      global: { components: { VTextField: Field, VSelect: Field, VSwitch: Field } },
    });
    await flushPromises();
    const actual = calls.flatMap(call => call.fields);
    assert.deepEqual(actual.map(field => field.key), keys);
    for (const field of actual) {
      assert.equal(field.label, `manifest:${field.key}`);
      assert.deepEqual(field.validation, { minimum: 0, maximum: 3600 });
      assert.deepEqual(field.options, [{ label: "option", value: "value" }]);
    }
    if (delayKey) assert.equal(actual.find(field => field.key === delayKey).disabled, true);
    await wrapper.find("button").trigger("click");
    assert.equal(wrapper.emitted("update:modelValue")[0][0].enabled, true);
    if (directory === "cast_profile_enricher") assert.equal(calls[0].pluginId, editorKey);
    wrapper.unmount();
  });
}
