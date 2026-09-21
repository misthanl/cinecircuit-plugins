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
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__ = vue;
const { mount, flushPromises } = require("@vue/test-utils");
const { install } = await import("../../.build/cinecircuit_plugins/maoyan_rank/frontend.js");
const Fields = { name: "Fields", props: ["fields", "modelValue"], emits: ["update:modelValue"], render: () => vue.h("div") };
const Switch = { name: "Switch", props: ["label", "modelValue"], emits: ["update:modelValue"], render: () => vue.h("div") };
function editor(type = ["movie"], includeSchedule = false) {
  let component;
  install({ vue, ui: { components: { SchemaFields: Fields } }, registerContribution() {}, registerEditor(entry) { assert.equal(entry.key, "maoyan-rank"); component = entry.component; } });
  const fields = [
    ...(includeSchedule ? [{ key: "clear", input_type: "switch", label: "清理历史记录" }, { key: "cron", input_type: "cron", label: "执行周期" }] : []),
    { key: "type", options: ["movie", "web-movie", "web-heat", "web-tv", "zongyi"].map(value => ({ value, label: value })), required: true },
    { key: "num" }, { key: "web_movie_num" },
    ...["all", "tx", "iqy", "mg", "yk"].flatMap(key => [{ key: key + "_enabled" }, { key: key + "_num" }]),
  ];
  return mount(component, { props: { modelValue: { type, num: "3", all_enabled: true } }, attrs: { fields }, global: { stubs: { VSwitch: Switch } } });
}
test("rank editor groups movies and platforms, retains legacy counts and disables irrelevant inputs", () => {
  const wrapper = editor();
  assert.deepEqual(wrapper.findAll("h3").map(node => node.text()), ["电影榜单", "电视剧与综艺", "播出平台"]);
  const groups = wrapper.findAllComponents(Fields);
  assert.equal(groups[1].props("modelValue").web_movie_num, "3");
  assert.equal(groups[0].props("fields")[0].disabled, false);
  assert.equal(groups[1].props("fields")[0].disabled, true);
  assert(groups.slice(3).every(group => group.props("fields")[0].disabled));
  wrapper.unmount();
});
test("TV selection preserves film selection and platform values", async () => {
  const wrapper = editor();
  const tv = wrapper.findAllComponents(Fields)[2];
  tv.vm.$emit("update:modelValue", { type: ["zongyi"] });
  const next = wrapper.emitted("update:modelValue").at(-1)[0];
  assert.deepEqual(next.type, ["movie", "zongyi"]);
  assert.equal(next.num, "3");
  await wrapper.setProps({ modelValue: next });
  await flushPromises();
  const groups = wrapper.findAllComponents(Fields);
  assert.equal(groups[3].props("fields")[0].disabled, false);
  assert.equal(groups[4].props("fields")[0].disabled, false);
  assert.equal(groups[6].props("fields")[0].disabled, true);
  wrapper.unmount();
});
test("turning off final movie leaves explicit empty selection and requires a board", async () => {
  const wrapper = editor();
  wrapper.findAllComponents(Switch)[0].vm.$emit("update:modelValue", false);
  const next = wrapper.emitted("update:modelValue").at(-1)[0];
  assert.deepEqual(next.type, []);
  await wrapper.setProps({ modelValue: next });
  assert.equal(wrapper.findAllComponents(Fields)[2].props("fields")[0].required, true);
  wrapper.unmount();
});

test("single-page editor places schedule before ranking controls without tabs", () => {
  const wrapper = editor(["movie"], true);
  assert.deepEqual(wrapper.findAllComponents(Fields).slice(0, 2).map(field => field.props("fields")[0].key), ["clear", "cron"]);
  assert.equal(wrapper.find(".maoyan-rank-settings").element.firstElementChild.classList.contains("rank-schedule"), true);
  assert.equal(wrapper.find('[role="tablist"]').exists(), false);
  wrapper.unmount();
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
