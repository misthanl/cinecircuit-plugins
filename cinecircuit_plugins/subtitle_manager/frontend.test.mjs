import { test } from "node:test";
import { installSelectStub } from "../../tests/select-stub.mjs";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";
const require = createRequire(resolve("package.json"));
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>", { pretendToBeVisual: true });
for (const key of [
  "window",
  "document",
  "Element",
  "HTMLElement",
  "SVGElement",
  "Node",
  "MutationObserver",
  "requestAnimationFrame",
  "cancelAnimationFrame",
])
  globalThis[key] = dom.window[key];
// jsdom has no layout engine; resize delivery is covered by browser tests.
globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
const vue = require("vue");
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__ = vue;
const { install: installPlugin } = await import(
  "../../.build/cinecircuit_plugins/subtitle_manager/frontend.js"
);
const { mount, flushPromises, config } = require("@vue/test-utils");
config.global.stubs.VIcon = true;
config.global.components.VBtn = vue.defineComponent({
  props: { disabled: Boolean, loading: Boolean, variant: String, color: String },
  setup(props, { slots, attrs }) {
    return () => vue.h("button", { ...attrs, disabled: props.disabled || props.loading }, slots.default?.());
  },
});

// Every page fixture supplies the required SDK dialog component; render only
// the opened dialog, matching the host's modelValue contract.
const Dialog = vue.defineComponent({
  props: { modelValue: Boolean },
  emits: ["update:modelValue"],
  setup(props, { slots, attrs }) {
    return () => props.modelValue ? vue.h("div", attrs, slots.default?.()) : null;
  },
});
function install(sdk) {
  return installPlugin({ ...sdk, ui: { ...sdk.ui, components: { Dialog, ...sdk.ui?.components } } });
}

installSelectStub(vue, require("@vue/test-utils").config);

async function openOnlineAndSearch(wrapper) {
  await wrapper
    .findAll('[role="tab"]')
    .find((button) => button.text().includes("在线字幕"))
    .trigger("click");
  const submit = wrapper.get(".subtitle-online-search-submit");
  assert.equal(submit.text(), "搜索");
  assert.equal(submit.attributes("type"), "submit");
  await wrapper.get("form.subtitle-tab-search-controls").trigger("submit");
}

function statistics(run, fail = false) {
  let registration;
  const Box = {
    render() {
      return vue.h("div", this.$slots.default?.());
    },
  };
  const Button = {
    props: ["disabled"],
    render() {
      return vue.h(
        "button",
        { disabled: this.disabled },
        this.$slots.default?.(),
      );
    },
  };
  install({
    vue,
    ui: { components: { Dialog: Box, Card: Box, Button } },
    registerPage() {},
    registerContribution(value) {
      registration = value;
    },
    async request(path) {
      assert.equal(path, "/plugins/subtitle-manager/runs?limit=1");
      if (fail) throw Error("private");
      return { items: run ? [run] : [] };
    },
  });
  assert.equal(registration.slot, "plugin.statistics");
  return mount(registration.component, {
    props: { context: { close() {} } },
    global: { stubs: { VIcon: true } },
  });
}

test("statistics render media counts, bilingual details, reasons and pagination", async () => {
  const wrapper = statistics({
    status: "success",
    result: {
      statistics: {
        media: 9,
        saved: 8,
        skipped: 1,
        failed: 0,
        completed_media: 8,
        bilingual: 8,
        converted: 2,
        rows: Array.from({ length: 9 }, (_, i) => ({
          media: `电影${i}`,
          provider: "ASSRT",
          language: "zh-CN-en",
          format: "ASS",
          status: "saved",
          reason: "测试原因",
        })),
      },
    },
  });
  await flushPromises();
  assert.deepEqual(
    wrapper.findAll(".metrics strong").map((n) => n.text()),
    ["9", "8", "1", "0"],
  );
  assert.equal(wrapper.find(".summary").exists(), false);
  assert.equal(wrapper.findAll(".metrics article").length, 4);
  assert.equal(
    wrapper.findAll(
      ".metrics small, .metrics .metric-icon, .metrics v-icon-stub",
    ).length,
    0,
  );
  assert.deepEqual(
    wrapper.findAll(".metrics h3").map((n) => n.text()),
    ["检查媒体", "保存字幕", "已跳过", "处理失败"],
  );
  assert.match(wrapper.text(), /简体中英双语/);
  assert.equal(wrapper.findAll("tbody tr").length, 8);
  await wrapper.get('[aria-label="查看处理原因"]').trigger("click");
  assert.match(wrapper.text(), /测试原因/);
  await wrapper.get('[aria-label="下一页"]').trigger("click");
  assert.equal(wrapper.findAll("tbody tr").length, 1);
  assert.match(wrapper.text(), /电影8/);
  wrapper.unmount();
});

test("missing numeric statistics display zero without using directory subtitle totals", async () => {
  for (const result of [
    { media_count: 3 },
    { media_count: 3, subtitle_count: 7 },
  ]) {
    const wrapper = statistics({ status: "success", result });
    await flushPromises();
    assert.deepEqual(
      wrapper.findAll(".metrics strong").map((n) => n.text()),
      ["3", "0", "0", "0"],
    );
    wrapper.unmount();
  }
  const empty = statistics(null);
  await flushPromises();
  assert.deepEqual(
    empty.findAll(".metrics strong").map((n) => n.text()),
    ["0", "0", "0", "0"],
  );
  assert.doesNotMatch(empty.text(), /本次处理|尚未执行/);
  empty.unmount();
  const wrapper = statistics(null, true);
  await flushPromises();
  assert.match(wrapper.get('[role="alert"]').text(), /加载失败/);
  assert.doesNotMatch(wrapper.text(), /private/);
  wrapper.unmount();
});

const SchemaFields = {
  name: "SchemaFields",
  props: ["fields", "modelValue"],
  emits: ["update:modelValue"],
  render() {
    return vue.h(
      "div",
      this.fields.map((field) => field.label || field.key).join(" "),
    );
  },
};
const SecretInput = {
  name: "SecretInput",
  props: ["modelValue", "type", "label"],
  emits: ["update:modelValue", "click:append-inner"],
  render() {
    return vue.h("input", { type: this.type, value: this.modelValue });
  },
};
function onlineEditor(modelValue = {}) {
  let editor;
  const calls = [];
  const keys = [
    "online_providers",
    "online_use_proxy",
    "subhd_url",
    "zimuku_url",
    "assrt_api_url",
    "assrt_api_key",
    "opensubtitles_api_url",
    "opensubtitles_api_key",
    "opensubtitles_username",
    "opensubtitles_password",
  ];
  keys.push("assrt_search_url", "subdl_api_url", "subdl_api_key", "shooter_api_url", "xunlei_api_url");
  const fields = keys.map((key) => ({
    key,
    label: key,
    secret: key.endsWith("_key") || key.endsWith("_password"),
    ...(key === "online_providers" ? {
      default: ["subhd", "zimuku"],
      options: [
        { value: "subhd", label: "SubHD" },
        { value: "zimuku", label: "字幕库" },
        { value: "assrt", label: "ASSRT" },
        { value: "opensubtitles", label: "OpenSubtitles" },
      ],
    } : {}),
  }));
  install({
    vue,
    ui: { components: { SchemaFields } },
    registerPage() {},
    registerEditor(value) {
      assert.equal(value.key, "subtitle-manager:online");
      editor = value.component;
    },
    async request(path) {
      calls.push(path);
      return { value: "saved-test-secret" };
    },
  });
  return {
    calls,
    wrapper: mount(editor, {
      props: { modelValue },
      attrs: { fields },
      global: { stubs: { VTextField: SecretInput } },
    }),
  };
}

test("online sources only show selected groups and preserve hidden settings", async () => {
  const { wrapper, calls } = onlineEditor({
    online_providers: ["subhd", "zimuku"],
    assrt_api_key: "keep",
    opensubtitles_username: "keep-user",
  });
  assert.deepEqual(
    wrapper.findAll("h3").map((node) => node.text()),
    ["SubHD", "字幕库"],
  );
  assert.deepEqual(
    wrapper
      .findAllComponents(SchemaFields)
      .slice(0, 2)
      .map((node) => node.props("fields")[0].key),
    ["online_providers", "online_use_proxy"],
  );
  assert.deepEqual(calls, []);
  const next = {
    online_providers: [],
    assrt_api_key: "keep",
    opensubtitles_username: "keep-user",
  };
  assert.equal(next.assrt_api_key, "keep");
  assert.equal(next.opensubtitles_username, "keep-user");
  await wrapper.setProps({ modelValue: next });
  assert.equal(wrapper.findAll("h3").length, 0);
  wrapper.unmount();
});

test("API keys and password reuse saved secret masking, reveal and edits without clear switches", async () => {
  const { wrapper, calls } = onlineEditor({
    online_providers: ["assrt", "opensubtitles"],
  });
  await flushPromises();
  assert.deepEqual(
    wrapper.findAll("h3").map((node) => node.text()),
    ["ASSRT", "OpenSubtitles"],
  );
  assert.match(wrapper.text(), /assrt_search_url/);
  assert.deepEqual(
    calls,
    ["assrt_api_key", "opensubtitles_api_key", "opensubtitles_password"].map(
      (key) => `/plugins/subtitle-manager/config/secret/${key}`,
    ),
  );
  const secrets = wrapper.findAllComponents(SecretInput);
  assert.equal(secrets.length, 3);
  assert(
    secrets.every(
      (node) =>
        node.props("type") === "password" &&
        node.props("modelValue") === "saved-test-secret",
    ),
  );
  assert.equal(wrapper.emitted("update:modelValue"), undefined);
  secrets[0].vm.$emit("click:append-inner");
  await flushPromises();
  assert.equal(secrets[0].props("type"), "text");
  secrets[0].vm.$emit("update:modelValue", "replacement");
  assert.equal(
    wrapper.emitted("update:modelValue").at(-1)[0].assrt_api_key,
    "replacement",
  );
  assert.doesNotMatch(wrapper.text(), /清除已保存/);
  assert(
    wrapper
      .findAllComponents(SchemaFields)
      .every((node) => node.props("fields").every((field) => !field.secret)),
  );
  wrapper.unmount();
});

test("Subtitle Manager uses structured identity for real download, preview and confirm", async () => {
  const paths = [];
  const requests = [];
  let registration;
  const Alert = {
    props: ["type"],
    render() {
      return vue.h(
        "div",
        { class: ["v-alert", `text-${this.type}`] },
        this.$slots.default?.(),
      );
    },
  };
  install({
    vue,
    ui: { components: { Alert } },
    request: async (path, init) => {
      paths.push(path);
      requests.push({ path, init });
      if (path.startsWith("/plugins/subtitle-manager/api/catalog?")) {
        return {
          items: [
            {
              path: "D:/media/示例剧.S01E02.strm",
              title: "示例剧.S01E02",
              identity: {
                title: "示例剧",
                media_type: "tv",
                year: 2026,
                season: 1,
                episode: 2,
                tmdb_id: "42",
              },
              subtitles: [{ name: "示例剧.zh.srt", size: 2048 }],
            },
          ],
        };
      }
      if (path === "/plugins/subtitle-manager/api/online-search") {
        return {
          identity: {
            title: "示例剧",
            media_type: "tv",
            year: 2026,
            season: 1,
            episode: 2,
          },
          sources: [
            {
              provider: "OpenSubtitles",
              state: "ready",
              candidate_count: 1,
              raw_candidate_count: 2,
              errors: [],
            },
            {
              provider: "字幕库",
              state: "restricted",
              candidate_count: 0,
              errors: [{ kind: "captcha", message: "需要验证码" }],
            },
          ],
          items: [
            {
              title: "示例剧 S01E02 中文字幕",
              provider: "OpenSubtitles",
              language: "zh-CN",
              format: "srt",
              url: "https://example.test/subtitle",
              candidate_handle: "candidate-1",
              score: 95,
              match_reason: "片名和季集匹配",
              tags: ["官方字幕", "双语", "简体", "英语", "SRT"],
              downloadable: true,
            },
          ],
          manual_actions: [
            {
              provider: "字幕库",
              url: "https://zmk.example/search",
              reason: "需要验证码",
            },
          ],
        };
      }
      if (path === "/plugins/subtitle-manager/api/online-preview") {
        return {
          preview_handle: "preview-1",
          items: [
            {
              index: 0,
              name: "示例剧.S01E02.zh-CN.srt",
              language: "zh-CN",
              format: "SRT",
              bytes: 100,
              excerpt: "00:00:01,000 --> 00:00:02,000\n测试字幕",
            },
            {
              index: 1,
              name: "示例剧.S01E03.zh-CN.ass",
              language: "zh-CN",
              format: "ASS",
              bytes: 120,
              excerpt: "Dialogue: 0,0:00:03.00,0:00:04.00,测试第二个字幕",
            },
          ],
        };
      }
      if (path === "/plugins/subtitle-manager/api/online-confirm") {
        return {
          saved: [{ subtitle_path: "D:/media/示例剧.S01E02.zh-CN.srt" }],
          errors: [],
        };
      }
      if (path === "/plugins/subtitle-manager/api/adjust") {
        return { adjusted_count: 18 };
      }
      if (path === "/plugins/subtitle-manager/api/delete") {
        return { deleted: true };
      }
      throw new Error(`unexpected request: ${path}`);
    },
    registerPage: (value) => {
      registration = value;
    },
  });

  assert.deepEqual(
    {
      pluginId: registration.pluginId,
      route: registration.route,
      title: registration.title,
    },
    {
      pluginId: "subtitle-manager",
      route: "plugin-subtitle-manager",
      title: "字幕管理",
    },
  );
  const wrapper = mount(registration.component);
  await flushPromises();
  await wrapper
    .findAll("button")
    .find((button) => button.text() === "上传字幕")
    ?.trigger("click");
  await flushPromises();
  assert.equal(
    wrapper.findComponent({ name: "VSelect" }).exists() ||
      wrapper.text().includes("自动识别"),
    true,
  );
  await wrapper.get('[aria-label="关闭上传字幕窗口"]').trigger("click");
  assert.match(wrapper.text(), /示例剧/);
  assert.match(wrapper.text(), /S01E02/);
  assert.match(wrapper.text(), /TMDB 42/);
  assert.match(wrapper.text(), /示例剧\.zh\.srt/);
  assert.doesNotMatch(wrapper.text(), /已读取 1 个本地媒体文件/);
  assert.equal(wrapper.find(".subtitle-browser").exists(), true);
  assert.equal(wrapper.find(".subtitle-toolbar").exists(), false);
  assert.equal(wrapper.get(".subtitle-sidebar-tools").find('[aria-label="刷新媒体目录"]').exists(), true);
  assert.equal(wrapper.find(".subtitle-sidebar").exists(), true);
  assert.equal(wrapper.findAll(".subtitle-online-panel").length, 0);
  assert.equal(wrapper.get('[role="tab"][aria-selected="true"]').text(), "本地字幕");
  assert.equal(
    wrapper.get(".subtitle-local-file .subtitle-file-copy strong").attributes("title"),
    "示例剧.zh.srt",
  );
  assert.doesNotMatch(wrapper.text(), /已安装字幕/);
  assert.equal(wrapper.get(".subtitle-content-tabs").find('[aria-haspopup="dialog"]').text(), "上传字幕");
  assert.doesNotMatch(wrapper.text(), /尚未发现外挂字幕/);
  assert.equal(wrapper.find(".subtitle-hero").exists(), false);
  assert.equal(
    dom.window.getComputedStyle(wrapper.get(".subtitle-detail").element).overflow,
    "hidden",
  );
  assert.equal(
    dom.window.getComputedStyle(wrapper.get(".subtitle-list").element).overflow,
    "auto",
  );
  assert.doesNotMatch(wrapper.text(), /SUBTITLE WORKSPACE|ASSRT 手动搜索/);

  await openOnlineAndSearch(wrapper);
  await flushPromises();
  const onlineControls = wrapper.get("form.subtitle-tab-search-controls").element;
  assert.deepEqual(
    [...onlineControls.children].map((item) => item.className),
    ["subtitle-sidebar-search subtitle-tab-search", "subtitle-season-toggle", "subtitle-online-search-submit"],
  );
  assert.equal(
    dom.window.getComputedStyle(wrapper.get(".subtitle-online-search-submit").element).height,
    dom.window.getComputedStyle(wrapper.get(".subtitle-online-query").element).height,
  );
  assert.equal(paths.includes("/plugins/subtitle-manager/api/online-search"), true);
  assert.equal(wrapper.findAll(".subtitle-online-panel").length, 1);
  assert.equal(
    dom.window.getComputedStyle(wrapper.get(".subtitle-online-results .subtitle-file-list").element)
      .overflow,
    "auto",
  );
  assert.equal(wrapper.findAll(".subtitle-upload-section").length, 0);
  const onlineSearchRequest = requests.find(
    (request) => request.path === "/plugins/subtitle-manager/api/online-search",
  );
  assert.deepEqual(JSON.parse(onlineSearchRequest.init.body), {
    media_path: "D:/media/示例剧.S01E02.strm",
    query: "示例剧 S01E02",
    season_pack: false,
  });
  assert.match(wrapper.text(), /OpenSubtitles/);
  assert.match(wrapper.text(), /zh-CN/);
  assert.match(wrapper.text(), /SRT/);
  assert.match(wrapper.text(), /95 分/);
  const openSubtitlesSource = wrapper
    .findAll(".subtitle-source")
    .find((source) => source.text().includes("OpenSubtitles"));
  assert.match(openSubtitlesSource.text(), /1\/2/);
  assert.match(openSubtitlesSource.attributes("title"), /1 条匹配，源站返回 2 条/);
  assert.equal(wrapper.find(".subtitle-candidate-tag").exists(), false);
  assert.doesNotMatch(wrapper.text(), /片名和季集匹配/);
  assert.match(wrapper.text(), /需要验证码/);
  assert.match(wrapper.get(".subtitle-host-notice").text(), /搜索完成找到 1 条在线字幕/);
  assert.equal(wrapper.get(".subtitle-host-notice").classes().includes("text-info"), true);
  assert.equal(wrapper.get(".subtitle-provider-mark").text(), "O");
  assert.equal(wrapper.find(".subtitle-source b").exists(), false);
  assert.equal(
    wrapper.get(".subtitle-online-file .subtitle-file-copy strong").attributes("title"),
    "示例剧 S01E02 中文字幕",
  );
  assert.equal(wrapper.findAll('.subtitle-online-file input[type="radio"]').length, 0);
  assert.equal(wrapper.find(".subtitle-preview-action").exists(), false);
  assert.equal(
    dom.window.getComputedStyle(
      wrapper.get(".subtitle-online-file .subtitle-file-copy strong").element,
    ).cursor,
    "default",
  );
  const sourceCards = wrapper.findAll(".subtitle-source");
  assert(sourceCards.every((card) => card.element.tagName === "BUTTON"));
  const sourceRail = wrapper.get(".subtitle-source-list");
  Object.defineProperties(sourceRail.element, {
    clientWidth: { configurable: true, value: 300 },
    scrollWidth: { configurable: true, value: 900 },
    scrollLeft: { configurable: true, writable: true, value: 0 },
  });
  let requestedScroll = 0;
  sourceRail.element.scrollBy = ({ left }) => { requestedScroll = left; };
  await sourceRail.trigger("scroll");
  assert.equal(wrapper.get('.subtitle-source-navigation').attributes("aria-label"), "字幕源导航");
  assert.equal(wrapper.get('.subtitle-source-arrow.is-left').attributes("disabled"), "");
  assert.equal(wrapper.get('.subtitle-source-arrow.is-right').attributes("aria-label"), "查看右侧字幕源");
  assert.equal(wrapper.get('.subtitle-source-arrow.is-right').attributes("disabled"), undefined);
  await wrapper.get('.subtitle-source-arrow.is-right').trigger("click");
  assert(requestedScroll > 0);
  sourceRail.element.scrollLeft = 600;
  await sourceRail.trigger("scroll");
  assert.equal(wrapper.get('.subtitle-source-arrow.is-left').attributes("aria-label"), "查看左侧字幕源");
  assert.equal(wrapper.get('.subtitle-source-arrow.is-left').attributes("disabled"), undefined);
  assert.equal(wrapper.get('.subtitle-source-arrow.is-right').attributes("disabled"), "");
  const zimukuCard = sourceCards.find((card) => card.text().includes("字幕库"));
  assert.equal(zimukuCard.text(), "字幕库");
  await zimukuCard.trigger("click");
  assert.equal(zimukuCard.attributes("aria-pressed"), "true");
  assert.equal(wrapper.findAll(".subtitle-online-file").length, 0);
  assert.match(wrapper.text(), /字幕库 暂无匹配字幕/);
  await zimukuCard.trigger("click");
  assert.equal(wrapper.findAll(".subtitle-online-file").length, 1);
  await wrapper.get(".subtitle-online-file .subtitle-action-trigger").trigger("click");
  assert.equal(
    wrapper.get('a[href="https://example.test/subtitle"]').attributes("target"),
    "_blank",
  );
  assert.equal(
    wrapper.get('a[href="https://zmk.example/search"]').attributes("target"),
    "_blank",
  );
  await wrapper.get(".subtitle-online-file .subtitle-download-action").trigger("click");
  assert.doesNotMatch(wrapper.find(".subtitle-host-notice").text(), /搜索完成|找到 1 条在线字幕/);
  await flushPromises();
  assert.equal(paths.at(-1), "/plugins/subtitle-manager/api/online-preview");
  assert.equal(wrapper.get(".subtitle-preview-dialog").attributes("aria-modal"), "true");
  assert.equal(wrapper.findAll(".subtitle-preview-file").length, 2);
  assert.match(wrapper.text(), /测试字幕/);
  await wrapper.findAll(".subtitle-preview-file-open")[1].trigger("click");
  assert.match(wrapper.get(".subtitle-preview-excerpt").text(), /测试第二个字幕/);
  await wrapper.findAll('.subtitle-preview-file > input[type="checkbox"]')[0].setValue(false);
  assert.match(wrapper.get(".subtitle-preview-footer").text(), /已选择 1 \/ 2/);
  await wrapper
    .findAll("button")
    .find((button) => button.text() === "保存所选")
    .trigger("click");
  await flushPromises();
  assert(paths.includes("/plugins/subtitle-manager/api/online-confirm"));
  const confirmation = requests.find(
    (request) => request.path === "/plugins/subtitle-manager/api/online-confirm",
  );
  assert.deepEqual(JSON.parse(confirmation.init.body).selected, [1]);
  await wrapper
    .findAll('[role="tab"]')
    .find((button) => button.text().includes("本地字幕"))
    .trigger("click");
  await wrapper.get(".subtitle-local-file .subtitle-action-trigger").trigger("click");
  await wrapper
    .findAll("button")
    .find((button) => button.text() === "调轴")
    .trigger("click");
  assert.equal(wrapper.get('[role="dialog"]').attributes("aria-modal"), "true");
  assert.match(wrapper.text(), /正数延后字幕，负数提前字幕/);
  await wrapper.get(".subtitle-adjustment-field input").setValue("-1.5");
  await wrapper.get(".subtitle-dialog").trigger("submit");
  await flushPromises();
  const adjustment = requests.find(
    (request) => request.path === "/plugins/subtitle-manager/api/adjust",
  );
  assert.deepEqual(JSON.parse(adjustment.init.body), {
    media_path: "D:/media/示例剧.S01E02.strm",
    subtitle_name: "示例剧.zh.srt",
    offset_seconds: -1.5,
  });
  assert.equal(wrapper.find('[role="dialog"]').exists(), false);
  await wrapper.get(".subtitle-local-file .subtitle-action-trigger").trigger("click");
  await wrapper
    .findAll('[role="menuitem"]')
    .find((button) => button.text() === "删除")
    .trigger("click");
  const deleteDialog = wrapper.get('[role="dialog"]');
  assert.equal(deleteDialog.attributes("aria-modal"), "true");
  assert.match(deleteDialog.text(), /删除字幕/);
  assert.match(deleteDialog.text(), /示例剧\.zh\.srt/);
  assert.doesNotMatch(deleteDialog.text(), /取消/);
  assert.equal(paths.includes("/plugins/subtitle-manager/api/delete"), false);
  await deleteDialog.trigger("submit");
  await flushPromises();
  const deletion = requests.find(
    (request) => request.path === "/plugins/subtitle-manager/api/delete",
  );
  assert.deepEqual(JSON.parse(deletion.init.body), {
    media_path: "D:/media/示例剧.S01E02.strm",
    subtitle_name: "示例剧.zh.srt",
  });
  assert.equal(wrapper.find('[role="dialog"]').exists(), false);
  wrapper.unmount();
});

test("Subtitle Manager discards search results after switching media", async () => {
  let registration;
  let resolveSearch;
  install({
    vue,
    request: async (path) => {
      if (path.startsWith("/plugins/subtitle-manager/api/catalog?")) {
        return {
          items: [
            {
              path: "D:/media/A.S01E01.strm",
              title: "A",
              identity: { title: "A", media_type: "tv", season: 1, episode: 1 },
            },
            {
              path: "D:/media/B.S01E01.strm",
              title: "B",
              identity: { title: "B", media_type: "tv", season: 1, episode: 1 },
            },
          ],
        };
      }
      if (path === "/plugins/subtitle-manager/api/online-search") {
        return new Promise((resolveSearchResult) => {
          resolveSearch = resolveSearchResult;
        });
      }
      if (path.includes("/inventory?")) return { items: [] };
      if (path.includes("/detail?") || path.includes("/poster?")) return {};
      throw new Error(`unexpected request: ${path}`);
    },
    registerPage: (value) => {
      registration = value;
    },
  });
  const wrapper = mount(registration.component);
  await flushPromises();
  assert.match(
    wrapper.get(".subtitle-local-list .subtitle-table-empty").text(),
    /暂无本地字幕/,
  );
  await openOnlineAndSearch(wrapper);
  assert.equal(wrapper.find(".subtitle-empty-files").exists(), false);
  await wrapper.findAll(".subtitle-media")[1].trigger("click");
  resolveSearch({
    identity: { title: "A", media_type: "tv", season: 1, episode: 1 },
    items: [
      {
        title: "A candidate",
        provider: "test",
        candidate_handle: "stale",
        downloadable: true,
      },
    ],
  });
  await flushPromises();
  assert.match(wrapper.text(), /B/);
  assert.doesNotMatch(wrapper.text(), /A candidate/);
  wrapper.unmount();
});

test("Subtitle Manager clears an old preview before previewing another candidate", async () => {
  let registration;
  let previewCalls = 0;
  install({
    vue,
    request: async (path) => {
      if (path.startsWith("/plugins/subtitle-manager/api/catalog?")) {
        return {
          items: [
            {
              path: "D:/media/A.mkv",
              title: "A",
              identity: { title: "A", media_type: "movie" },
            },
          ],
        };
      }
      if (path === "/plugins/subtitle-manager/api/online-search") {
        return {
          identity: { title: "A", media_type: "movie" },
          items: [
            {
              title: "candidate one",
              provider: "test",
              candidate_handle: "one",
              downloadable: true,
            },
            {
              title: "candidate two",
              provider: "test",
              candidate_handle: "two",
              downloadable: true,
            },
          ],
        };
      }
      if (path === "/plugins/subtitle-manager/api/online-preview") {
        previewCalls += 1;
        if (previewCalls === 1) {
          return {
            preview_handle: "old-preview",
            items: [
              {
                index: 0,
                name: "old.srt",
                language: "zh",
                format: "SRT",
                bytes: 10,
                excerpt: "old excerpt",
              },
            ],
          };
        }
        throw new Error("new preview failed");
      }
      throw new Error(`unexpected request: ${path}`);
    },
    registerPage: (value) => {
      registration = value;
    },
  });
  const wrapper = mount(registration.component);
  await flushPromises();
  await openOnlineAndSearch(wrapper);
  await flushPromises();
  await wrapper.findAll(".subtitle-action-trigger")[0].trigger("click");
  await wrapper.get(".subtitle-download-action").trigger("click");
  await flushPromises();
  assert.match(wrapper.text(), /old excerpt/);
  await wrapper.findAll(".subtitle-action-trigger")[1].trigger("click");
  await wrapper.get(".subtitle-download-action").trigger("click");
  await flushPromises();
  assert.doesNotMatch(wrapper.text(), /old excerpt|确认保存/);
  assert.match(wrapper.get('[role="alert"]').text(), /new preview failed/);
  wrapper.unmount();
});

test("Subtitle Manager displays and submits a source CAPTCHA before continuing search", async () => {
  let registration;
  const paths = [];
  install({
    vue,
    request: async (path, init) => {
      paths.push(path);
      if (path.startsWith("/plugins/subtitle-manager/api/catalog?")) {
        return {
          items: [
            {
              path: "D:/media/示例剧.S01E02.strm",
              title: "示例剧.S01E02",
              identity: {
                title: "示例剧",
                media_type: "tv",
                year: 2026,
                season: 1,
                episode: 2,
                tmdb_id: "42",
              },
            },
          ],
        };
      }
      if (path === "/plugins/subtitle-manager/api/online-search") {
        return {
          identity: { title: "示例剧", media_type: "tv", season: 1, episode: 2 },
          sources: [],
          items: [],
          manual_actions: [],
          captcha_challenges: [
            {
              handle: "captcha-1",
              provider: "字幕库",
              site: "zimuku",
              image: "data:image/bmp;base64,Qk1GAAAAAAAAAHsAAA==",
              instruction: "请输入页面中显示的 5 位数字验证码",
            },
          ],
        };
      }
      if (path === "/plugins/subtitle-manager/api/online-captcha") {
        assert.deepEqual(JSON.parse(init.body), {
          captcha_handle: "captcha-1",
          code: "12345",
        });
        return {
          identity: { title: "示例剧", media_type: "tv", season: 1, episode: 2 },
          sources: [],
          items: [
            {
              title: "示例剧 S01E02 中文字幕",
              provider: "字幕库",
              language: "zh-CN",
              format: "srt",
              candidate_handle: "candidate-after-captcha",
              downloadable: true,
            },
          ],
          manual_actions: [],
          captcha_challenges: [],
        };
      }
      throw new Error(`unexpected request: ${path}`);
    },
    registerPage: (value) => {
      registration = value;
    },
  });
  const wrapper = mount(registration.component);
  await flushPromises();
  await openOnlineAndSearch(wrapper);
  await flushPromises();
  assert.equal(wrapper.findAll(".subtitle-captcha-card").length, 1);
  assert.equal(
    wrapper.get(".subtitle-captcha-image").attributes("src"),
    "data:image/bmp;base64,Qk1GAAAAAAAAAHsAAA==",
  );
  await wrapper.get(".subtitle-captcha-input").setValue("12345");
  await wrapper
    .findAll("button")
    .find((button) => button.text() === "提交并继续搜索")
    .trigger("click");
  await flushPromises();
  assert.equal(paths.at(-1), "/plugins/subtitle-manager/api/online-captcha");
  assert.equal(wrapper.findAll(".subtitle-captcha-card").length, 0);
  assert.match(wrapper.text(), /示例剧 S01E02 中文字幕/);
  wrapper.unmount();
});

test("Subtitle Manager discards a pending CAPTCHA after changing media or starting another search", async () => {
  for (const action of ["media", "search"]) {
    let registration;
    let resolveCaptcha;
    let searches = 0;
    install({
      vue,
      registerPage(value) { registration = value; },
      async request(path) {
        if (path.includes("/catalog?")) return { items: [
          { path: "A.mkv", title: "A", identity: { title: "A" } },
          { path: "B.mkv", title: "B", identity: { title: "B" } },
        ] };
        if (path.endsWith("/online-search")) return {
          identity: {}, items: [], captcha_challenges: [{ handle: `captcha-${++searches}`, provider: "test", site: "test" }],
        };
        if (path.endsWith("/online-captcha")) return new Promise(resolve => { resolveCaptcha = resolve; });
        return {};
      },
    });
    const wrapper = mount(registration.component);
    await flushPromises();
    await openOnlineAndSearch(wrapper);
    await flushPromises();
    await wrapper.get(".subtitle-captcha-input").setValue("12345");
    await wrapper.findAll("button").find(button => button.text() === "提交并继续搜索").trigger("click");
    if (action === "media") await wrapper.findAll(".subtitle-media")[1].trigger("click");
    else await wrapper.get("form.subtitle-tab-search-controls").trigger("submit");
    await flushPromises();
    resolveCaptcha({ identity: {}, items: [{ title: "stale CAPTCHA result", provider: "test", candidate_handle: "old" }] });
    await flushPromises();
    assert.doesNotMatch(wrapper.text(), /stale CAPTCHA result/);
    if (action === "search") {
      await wrapper.get(".subtitle-captcha-input").setValue("54321");
      const submit = wrapper.findAll("button").find(button => button.text() === "提交并继续搜索");
      assert.equal(submit.element.disabled, false);
    }
    wrapper.unmount();
  }
});

test("Subtitle Manager allows a new candidate CAPTCHA while an old submission settles", async () => {
  for (const outcome of ["success", "failure"]) {
    let registration;
    let resolveOld;
    let rejectOld;
    let resolveCurrent;
    let submissions = 0;
    install({
      vue,
      registerPage(value) { registration = value; },
      async request(path, init) {
        if (path.includes("/catalog?")) return { items: [{ path: "A.mkv", title: "A", identity: { title: "A" } }] };
        if (path.endsWith("/online-search")) return {
          identity: {}, items: ["first", "second"].map(id => ({ title: id, provider: "test", candidate_handle: id, downloadable: true })),
        };
        if (path.endsWith("/online-preview")) return {
          captcha_required: true, captcha: { handle: JSON.parse(init.body).candidate_handle, provider: "test", site: "test" },
        };
        if (path.endsWith("/online-captcha")) {
          submissions += 1;
          if (submissions === 1) return new Promise((resolve, reject) => { resolveOld = resolve; rejectOld = reject; });
          return new Promise(resolve => { resolveCurrent = resolve; });
        }
        return {};
      },
    });
    const wrapper = mount(registration.component);
    await flushPromises();
    await openOnlineAndSearch(wrapper);
    await flushPromises();
    for (const index of [0, 1]) {
      const row = wrapper.findAll(".subtitle-online-file")[index];
      await row.get(".subtitle-action-trigger").trigger("click");
      await row.get(".subtitle-download-action").trigger("click");
      await flushPromises();
      await wrapper.get(".subtitle-captcha-input").setValue("12345");
      const submit = wrapper.findAll("button").find(button => button.text() === "提交并继续预览");
      assert.ok(submit, "new candidate exposes an enabled CAPTCHA submission");
      assert.equal(submit.element.disabled, false);
      await submit.trigger("click");
    }
    assert.equal(submissions, 2);
    if (outcome === "failure") rejectOld(new Error("stale CAPTCHA failure"));
    else resolveOld({ preview_handle: "stale", items: [] });
    await flushPromises();
    assert.doesNotMatch(wrapper.text(), /stale CAPTCHA failure|已下载并校验/);
    assert.equal(wrapper.findAll("button").find(button => button.text() === "提交中…").element.disabled, true);
    resolveCurrent({ preview_handle: "current", items: [] });
    await flushPromises();
    assert.match(wrapper.text(), /已下载并校验/);
    wrapper.unmount();
  }
});


test("recorded media pages render before subtitles and ignore stale selection responses", async () => {
  let registration;
  const requests = [];
  const inventoryResolvers = new Map();
  const detailResolvers = new Map();
  install({
    vue,
    registerPage(value) { registration = value; },
    async request(path) {
      requests.push(path);
      const url = new URL(path, "https://fixture.invalid");
      if (url.pathname.endsWith("/catalog")) return {
        items: [{ path: "/media/A.mkv", title: "A" }, { path: "/media/B.mkv", title: "B" }],
        has_more: true,
      };
      if (url.pathname.endsWith("/inventory")) return new Promise(resolve => inventoryResolvers.set(url.searchParams.get("media_path"), resolve));
      if (url.pathname.endsWith("/detail")) return new Promise(resolve => detailResolvers.set(url.searchParams.get("media_path"), resolve));
      return {};
    },
  });
  const wrapper = mount(registration.component);
  await flushPromises();
  assert.equal(wrapper.findAll(".subtitle-media").length, 2);
  assert.equal(inventoryResolvers.size, 1, "only selected media reads subtitles");
  assert.match(wrapper.text(), /正在读取字幕/);
  await wrapper.findAll(".subtitle-media")[1].trigger("click");
  inventoryResolvers.get("/media/B.mkv")({ items: [{ name: "B.en.srt" }] });
  detailResolvers.get("/media/B.mkv")({ identity: { title: "B details" } });
  await flushPromises();
  inventoryResolvers.get("/media/A.mkv")({ items: [{ name: "A.stale.srt" }] });
  detailResolvers.get("/media/A.mkv")({ identity: { title: "A stale" } });
  await flushPromises();
  assert.match(wrapper.get(".subtitle-local-list").text(), /B.en.srt/);
  assert.doesNotMatch(wrapper.get(".subtitle-detail").text(), /A.stale|A stale/);
  await wrapper.findAll(".subtitle-pagination button")[1].trigger("click");
  await flushPromises();
  assert.ok(requests.some(path => path.includes("/catalog?") && path.includes("offset=100")));
  wrapper.unmount();
});

test("recorded media search discards older list responses", async () => {
  let registration;
  const pages = [];
  install({
    vue,
    registerPage(value) { registration = value; },
    async request(path) {
      if (path.includes("/catalog?")) return new Promise(resolve => pages.push({ path, resolve }));
      if (path.includes("/inventory?")) return { items: [] };
      return {};
    },
  });
  const wrapper = mount(registration.component);
  await flushPromises();
  await wrapper.get(".subtitle-sidebar-search input").setValue("目标");
  await wrapper.get(".subtitle-sidebar-search input").trigger("keyup", { key: "Enter" });
  assert.equal(pages.length, 2);
  assert.ok(pages[1].path.includes("offset=0"));
  pages[1].resolve({ items: [{ path: "/media/new.mkv", title: "目标" }], has_more: false });
  await flushPromises();
  pages[0].resolve({ items: [{ path: "/media/old.mkv", title: "旧结果" }], has_more: true });
  await flushPromises();
  assert.match(wrapper.get(".subtitle-list").text(), /目标/);
  assert.doesNotMatch(wrapper.get(".subtitle-list").text(), /旧结果/);
  assert.equal(wrapper.findAll(".subtitle-pagination button")[1].element.disabled, true);
  wrapper.unmount();
});


test("new subtitle sources expose endpoints and an encrypted SubDL secret field", async () => {
  const { wrapper, calls } = onlineEditor({ online_providers: ["subdl", "shooter", "xunlei"] });
  await flushPromises();
  assert.deepEqual(wrapper.findAll("h3").map(node => node.text()), ["SubDL", "射手影音", "迅雷看看"]);
  assert.deepEqual(calls, ["/plugins/subtitle-manager/config/secret/subdl_api_key"]);
  assert.equal(wrapper.findAllComponents(SecretInput).length, 1);
  assert.equal(wrapper.findComponent(SecretInput).props("type"), "password");
  for (const key of ["subdl_api_url", "shooter_api_url", "xunlei_api_url"]) {
    assert(wrapper.findAllComponents(SchemaFields).some(node => node.props("fields").some(field => field.key === key)));
  }
  wrapper.unmount();
});
