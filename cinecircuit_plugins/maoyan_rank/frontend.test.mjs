import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { readFileSync } from "node:fs";
const require = createRequire(resolve("package.json"));
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>");
for (const key of ["window", "document", "Element", "HTMLElement", "SVGElement", "Node"]) globalThis[key] = dom.window[key];
const vue = require("vue");
// Match the host bridge instead of masking missing exports with the entire Vue module.
const hostSource = readFileSync(new URL('../../../cinecircuit/frontend/src/extensions/runtime.ts', import.meta.url), 'utf8');
const exportedNames = hostSource.match(/value: Object\.freeze\(\{([\s\S]*?)\}\)/)[1].match(/\b\w+\b/g);
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__ = Object.fromEntries(exportedNames.map(key => [key, vue[key]]));
const { mount, flushPromises } = require("@vue/test-utils");
const { install } = await import("../../.build/cinecircuit_plugins/maoyan_rank/frontend.js");
const Fields = { name: "Fields", props: ["fields", "modelValue"], emits: ["update:modelValue"], render: () => vue.h("div") };
function editor(modelValue = {}, includeSchedule = false, request) {
  let component;
  install({ vue, request, ui: { components: { SchemaFields: Fields } }, registerContribution() {}, registerEditor(entry) { assert.equal(entry.key, "maoyan-rank"); component = entry.component; } });
  const fields = [
    ...(includeSchedule ? [{ key: "clear" }, { key: "cron" }] : []),
    { key: "movie_enabled" }, { key: "num" },
    { key: "platform_types", label: "媒体分类", multiple: true, options: ["movie", "tv", "anime", "variety", "documentary"].map(value => ({ value, label: value })) },
    ...["tx", "iqy", "mg", "yk"].flatMap(key => [{ key: key + "_enabled" }, { key: key + "_num" }]),
  ];
  return mount(component, { props: { modelValue }, attrs: { fields }, global: { stubs: { VTextField: { props: ["rules", "modelValue"], render: () => vue.h("div") } } } });
}
function field(wrapper, key) { return wrapper.findAllComponents(Fields).find(group => group.props("fields")[0].key === key); }

test("editor preserves category order and removes all-network and network-movie controls", () => {
  const wrapper = editor();
  assert.deepEqual(wrapper.findAll("h3").map(node => node.text()), ["猫眼电影榜单", "平台影视榜单", "播出平台"]);
  const categories = field(wrapper, "platform_types").props("fields")[0];
  assert.equal(categories.multiple, true);
  assert.equal(categories.label, "媒体分类");
  assert.deepEqual(categories.options.map(option => option.value), ["movie", "tv", "anime", "variety", "documentary"]);
  assert.equal(field(wrapper, "num").props("fields")[0].disabled, false);
  assert.equal(field(wrapper, "tx_enabled").props("fields")[0].disabled, true);
  wrapper.unmount();
});
test("legacy categories and all-network migrate without losing movie or count settings", async () => {
  const wrapper = editor({ type: ["movie", "web-tv", "web-heat", "zongyi"], num: "3", all_enabled: true });
  const types = field(wrapper, "platform_types");
  assert.deepEqual(types.props("modelValue").platform_types, ["tv", "variety"]);
  types.vm.$emit("update:modelValue", { platform_types: ["documentary"] });
  const next = wrapper.emitted("update:modelValue").at(-1)[0];
  assert.equal(next.movie_enabled, true);
  assert.equal(next.num, "3");
  assert.equal(next.tx_enabled, true);
  await wrapper.setProps({ modelValue: next });
  assert.equal(field(wrapper, "tx_num").props("fields")[0].disabled, false);
  assert.equal(field(wrapper, "mg_enabled").props("fields")[0].disabled, true);
  assert.equal(field(wrapper, "mg_num").props("fields")[0].disabled, true);
  wrapper.unmount();
});
test("explicit empty categories and disabled box office survive reopening", () => {
  const wrapper = editor({ type: ["movie", "web-heat"], all_enabled: true, platform_types: [], movie_enabled: false, tx_enabled: false });
  assert.deepEqual(field(wrapper, "platform_types").props("modelValue").platform_types, []);
  assert.equal(field(wrapper, "num").props("fields")[0].disabled, true);
  assert.equal(field(wrapper, "tx_enabled").props("modelValue").tx_enabled, false);
  wrapper.unmount();
});
test("schedule remains first without adding tabs", () => {
  const wrapper = editor({}, true);
  assert.deepEqual(wrapper.findAllComponents(Fields).slice(0, 2).map(field => field.props("fields")[0].key), ["clear", "cron"]);
  assert.equal(wrapper.find('[role="tablist"]').exists(), false);
  wrapper.unmount();
});

test("saved legacy configuration survives host-injected defaults even while the plugin is disabled", async () => {
  let done;
  const wrapper = editor({ movie_enabled: true, platform_types: [] }, false, (path) => {
    assert.equal(path, "/plugins/");
    return new Promise(resolve => { done = resolve; });
  });
  assert(wrapper.text().includes("正在读取"));
  done({ items: [{ id: "maoyan-rank", enabled: false, config: { type: ["web-heat"], tx_enabled: true, tx_num: "7" } }] });
  await flushPromises();
  const next = wrapper.emitted("update:modelValue").at(-1)[0];
  assert.equal(next.movie_enabled, false);
  assert.deepEqual(next.platform_types, ["tv"]);
  assert.equal(next.tx_num, "7");
  assert(!wrapper.text().includes("正在读取"));
  wrapper.unmount();
});

test("unmount aborts configuration loading without late updates", async () => {
  let done, signal;
  const wrapper = editor({}, false, (_path, init) => {
    signal = init.signal;
    return new Promise(resolve => { done = resolve; });
  });
  wrapper.unmount();
  assert.equal(signal.aborted, true);
  done({ items: [{ id: "maoyan-rank", config: {} }] });
  await flushPromises();
  assert.equal(wrapper.emitted("update:modelValue"), undefined);
});

async function statistics(latest = true, records = [], requestOverride) {
  let component;
  const Surface = { render() { return vue.h('div', this.$slots.default?.()); } };
  const Button = { props: ['disabled'], render() { return vue.h('button', { disabled: this.disabled }, this.$slots.default?.()); } };
  install({ vue, ui: { components: { Image: "img", Button, Card: Surface, Dialog: Surface, Alert: Surface } },
    registerContribution(entry) { component = entry.component; },
    request: requestOverride || (async () => ({ items: records, total: records.length, page: 1, pages: 1, cumulative: { checked: 25, subscribed: 10, existing: 12, retry: 3 }, latest_run: latest ? {
      status: 'completed', updated_at: '2026-09-08T06:30:00Z', checked: 2, subscribed: 1, existing: 0, retry: 1,
      items: [{ title: '成功作品', status: 'subscribed', retry: false, board: '电影票房榜', reason: '已添加订阅' },
              { title: '暂缓作品', status: 'unknown', retry: true, board: '全网热度榜', reason: '目标季不明确' }],
    } : null })),
  });
  const wrapper = mount(component, { props: { context: { close() {}, configure() {} } } });
  await flushPromises();
  return wrapper;
}

test('statistics details start collapsed, toggle and retry card filters without hiding history', async () => {
  const wrapper = await statistics();
  assert.equal(wrapper.find('#maoyan-run-details').exists(), false);
  assert(wrapper.text().includes('订阅历史'));
  await wrapper.findAll('button').find(button => button.text() === '查看明细').trigger('click');
  assert.equal(wrapper.findAll('tbody tr').length, 2);
  await wrapper.findAll('button').find(button => button.text() === '收起明细').trigger('click');
  assert.equal(wrapper.find('#maoyan-run-details').exists(), false);
  await wrapper.findAll('button').find(button => button.text() === '查看明细').trigger('click');
  await wrapper.findAll('button').find(button => button.text() === '待重试').trigger('click');
  assert.equal(wrapper.findAll('tbody tr').length, 1);
  assert(wrapper.find('tbody').text().includes('暂缓作品'));
  await wrapper.findAll('button').find(button => button.text() === '全部').trigger('click');
  assert.equal(wrapper.findAll('tbody tr').length, 2);
  wrapper.unmount();
});

test('pagination keeps the same statistics DOM and old cards during loading and errors', async () => {
  let resolvePage, rejectPage, calls = 0;
  const row = { id: 1, title: '第一页作品', subscribed_at: '2026-09-08T00:00:00Z' };
  const response = { items: [row], total: 9, page: 1, pages: 2, cumulative: { checked: 20 } };
  const wrapper = await statistics(false, [], () => ++calls === 1 ? Promise.resolve(response)
    : new Promise((resolve, reject) => { resolvePage = resolve; rejectPage = reject; }));
  const section = wrapper.get('.maoyan-statistics').element;
  const grid = wrapper.get('.maoyan-statistics__grid').element;
  grid.getBoundingClientRect = () => ({ height: 248 });
  const next = () => wrapper.get('[aria-label="订阅记录分页"]').findAll('button').at(-1);
  await next().trigger('click');
  assert.equal(wrapper.get('.maoyan-statistics').element, section);
  assert(wrapper.text().includes('第一页作品'));
  assert.equal(wrapper.get('.maoyan-statistics__grid').attributes('aria-busy'), 'true');
  assert.equal(grid.style.minHeight, '248px');
  assert.equal(next().element.disabled, true);
  rejectPage(new Error('加载失败'));
  await flushPromises();
  assert.equal(wrapper.get('.maoyan-statistics').element, section);
  assert(wrapper.text().includes('第一页作品'));
  assert(wrapper.find('[role="alert"]').exists());
  await next().trigger('click');
  resolvePage({ ...response, page: 2, items: [{ ...row, id: 2, title: '第二页作品' }] });
  await flushPromises();
  assert.equal(wrapper.get('.maoyan-statistics').element, section);
  assert(wrapper.text().includes('第二页作品'));
  assert(!wrapper.text().includes('第一页作品'));
  assert.equal(grid.style.minHeight, '248px');
  wrapper.unmount();
});

test('statistics with no snapshot does not invent counts or expand empty details', async () => {
  const wrapper = await statistics(false);
  assert(!wrapper.text().includes('本次运行'));
  assert.deepEqual(wrapper.findAll('.maoyan-statistics__metrics dd').map(node => node.text()), ['25', '10', '12', '3']);
  assert.equal(wrapper.find('#maoyan-run-details').exists(), false);
  wrapper.unmount();
});

test('statistics dialog caps desktop width while preserving viewport gutters', async () => {
  const wrapper = await statistics();
  const dialog = wrapper.find('[max-width]');
  assert.equal(dialog.attributes('max-width'), '1000');
  assert.equal(dialog.attributes('width'), 'calc(100vw - 32px)');
  wrapper.unmount();
});

test('history gallery retains metadata to the right of a safe portrait poster', async () => {
  const wrapper = await statistics(true, [{ id: 1, title: '示例作品', poster: 'https://example.test/poster.jpg',
    media_label: '综艺', platform: '示例平台', release_info: '上线34天', subscribed_at: '2026-09-08T00:00:00Z' }]);
  const card = wrapper.get('.maoyan-subscription');
  assert.equal(card.element.children[0].className, 'maoyan-subscription__poster');
  assert.equal(card.element.children[1].className, 'maoyan-subscription__body');
  for (const text of ['示例作品', '综艺', '示例平台', '上线34天']) assert(card.text().includes(text));
  const timeLines = card.findAll('.maoyan-subscription__time time span');
  assert.equal(timeLines.length, 2);
  assert.match(timeLines[0].text(), /^订阅时间：\d{4}-\d{2}-\d{2}$/);
  assert.match(timeLines[1].text(), /^\d{2}:\d{2}:\d{2}$/);
  assert(card.get('.maoyan-subscription__time time').attributes('aria-label').startsWith('订阅时间：'));
  await card.get('img').trigger('error');
  assert(card.text().includes('无海报'));
  const source = readFileSync(new URL('./StatisticsView.vue', import.meta.url), 'utf8');
  assert(source.includes('grid-template-columns: 64px minmax(0, 1fr)'));
  assert(source.includes('grid-template-rows: 96px'));
  assert(source.includes('height: 96px; max-height: 96px; overflow: hidden'));
  assert.equal(card.get('.maoyan-subscription__release').attributes('title'), '上线34天');
  assert(card.get('.maoyan-subscription__time').attributes('title').includes('2026-09-08'));
  assert(source.includes('grid-template-columns: repeat(4, minmax(0, 1fr))'));
  for (const width of [1100, 850, 600]) assert(source.includes(`max-width: ${width}px`));
  wrapper.unmount();
});

test("statistics delegates protected posters to the host authenticated image component", async () => {
  let statistics;
  const Shell = { render() { return vue.h("div", this.$slots.default?.()); } };
  const Image = { props: ["src"], emits: ["error"], render() { return vue.h("span", { "data-protected-source": this.src }); } };
  install({ vue, ui: { components: { Button: Shell, Card: Shell, Dialog: Shell, Alert: Shell, Image } }, registerEditor() {}, registerContribution(entry) { statistics = entry.component; },
    request: async () => ({ items: [{ id: 1, title: "Fixture", poster: "https://image.tmdb.org/t/p/w500/test.jpg", subscribed_at: "2026-09-21T00:00:00Z" }], total: 1, page: 1, pages: 1 }) });
  const wrapper = mount(statistics, { props: { context: { close() {} } } });
  await flushPromises();
  const image = wrapper.findComponent(Image);
  assert(image.exists());
  assert(image.props("src").startsWith("/explore/image-proxy?source_key=tmdb&url="));
  assert.equal(wrapper.findAll("img").length, 0);
  image.vm.$emit("error", new Error("fixture"));
  await flushPromises();
  assert.equal(wrapper.findComponent(Image).exists(), false);
  wrapper.unmount();
});


test("legacy fields are migrated but never submitted when opening or editing settings", async () => {
  const legacy = { type: ["web-tv", "zongyi"], all_enabled: true, all_num: "20", web_movie_num: "10", tx_num: "7", cron: "0 6 * * *" };
  const wrapper = editor({}, true, async () => ({ items: [{ id: "maoyan-rank", config: legacy }] }));
  await flushPromises();
  const opened = wrapper.emitted("update:modelValue").at(-1)[0];
  for (const key of ["type", "all_enabled", "all_num", "web_movie_num"]) assert.equal(key in opened, false);
  assert.deepEqual(opened.platform_types, ["tv", "variety"]);
  assert.equal(opened.movie_enabled, false);
  assert.equal(opened.tx_enabled, true);
  assert.equal(opened.tx_num, "7");
  assert.equal(opened.cron, legacy.cron);
  await wrapper.setProps({ modelValue: opened });
  field(wrapper, "platform_types").vm.$emit("update:modelValue", { ...legacy, platform_types: ["anime"] });
  const saved = wrapper.emitted("update:modelValue").at(-1)[0];
  for (const key of ["type", "all_enabled", "all_num", "web_movie_num"]) assert.equal(key in saved, false);
  assert.deepEqual(saved.platform_types, ["anime"]);
  wrapper.unmount();
});
