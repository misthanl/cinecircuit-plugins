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
const { install } = await import("../../.build/cinecircuit_plugins/douban_rank/frontend.js");
const { mount, flushPromises } = require("@vue/test-utils");
const Box = { setup: (_, { slots }) => () => vue.h("div", slots.default?.()) };
const Button = { props: ["disabled", "loading"], emits: ["click"], setup: (props, { slots, emit }) => () => vue.h("button", { disabled: props.disabled || props.loading, onClick: () => emit("click") }, slots.default?.()) };
test("Douban grouped editor preserves television and RSS settings when movies change", async () => {
  let editor;
  const Fields = { props: ["fields", "modelValue"], emits: ["update:modelValue"], setup: () => () => vue.h("div") };
  install({ vue, ui: { components: { Button, Card: Box, Dialog: Box, Alert: Box, SchemaFields: Fields } }, registerEditor: value => { editor = value; }, registerContribution() {} });
  const wrapper = mount(editor.component, { props: { modelValue: { ranks: ["movie-real-time", "tv-hot"], rss_addrs: "/feed" } }, attrs: { fields: [{ key: "ranks", options: [{ value: "movie-real-time", label: "电影" }, { value: "tv-hot", label: "电视剧" }] }] } });
  const groups = wrapper.findAllComponents(Fields);
  assert.equal(groups.length, 2);
  groups[0].vm.$emit("update:modelValue", { ranks: [] });
  await vue.nextTick();
  assert.deepEqual(wrapper.emitted("update:modelValue")[0][0], { ranks: ["tv-hot"], rss_addrs: "/feed" });
  wrapper.unmount();
});
function component(request) {
  let contribution;
  install({ vue, request, ui: { components: { Button, Card: Box, Dialog: Box, Alert: Box } }, registerContribution: value => { contribution = value; } });
  assert.equal(contribution.slot, "plugin.statistics");
  return contribution.component;
}

test("Douban fetches its own API, paginates and handles failed posters", async () => {
  const paths = [];
  const page = { items: [{ id: 1, title: "作品一", poster: "https://img9.doubanio.com/poster.jpg", media_label: "电影", board: "热门综艺", rating: 8.6, subscribed_at: "invalid" }], total: 9, movie_count: 4, tv_count: 5, board_count: 2, page: 1, pages: 2, cumulative: { checked: 12, subscribed: 9, existing: 2, retry: 1 } };
  let configured = false;
  const wrapper = mount(component(async path => { paths.push(path); return { ...page, page: paths.length === 1 ? 1 : 2 }; }), { props: { context: { close() {}, configure: () => { configured = true; } } } });
  await flushPromises();
  assert.deepEqual(wrapper.findAll(".douban-statistics__metrics dd").map(item => item.text()), ["12", "9", "2", "1"]);
  assert.match(wrapper.get("img").attributes("src"), /^\/explore\/image-proxy\?source_key=douban/);
  await wrapper.get("img").trigger("error");
  assert.match(wrapper.get(".douban-subscription").text(), /无海报/);
  assert.match(wrapper.get(".douban-subscription").text(), /豆瓣评分 8.6/);
  assert.match(wrapper.get(".douban-subscription").text(), /未知时间/);
  await wrapper.findAll("button").find(button => button.text() === "下一页").trigger("click");
  await flushPromises();
  assert.deepEqual(paths, ["/plugins/douban-hot/api/statistics?page=1", "/plugins/douban-hot/api/statistics?page=2"]);
  assert.equal(wrapper.findAll("button").find(button => button.text() === "下一页").element.disabled, true);
  assert.equal(wrapper.find('[aria-label="配置豆瓣榜单"]').exists(), false);
  wrapper.unmount();
});

test("Douban retries errors and shows an empty history without a log table", async () => {
  let calls = 0;
  const wrapper = mount(component(async () => {
    if (++calls === 1) throw new Error("读取失败");
    return { items: [], total: 0, movie_count: 0, tv_count: 0, board_count: 0, page: 1, pages: 1 };
  }), { props: { context: { close() {}, configure() {} } } });
  await flushPromises();
  assert.match(wrapper.text(), /读取失败/);
  await wrapper.findAll("button").find(button => button.text() === "刷新").trigger("click");
  await flushPromises();
  assert.match(wrapper.text(), /暂无订阅记录/);
  assert.equal(wrapper.find("table").exists(), false);
  wrapper.unmount();
});
