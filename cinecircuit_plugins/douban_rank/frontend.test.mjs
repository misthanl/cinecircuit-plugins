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
function component(request) {
  let contribution;
  install({ vue, request, ui: { components: { Button, Card: Box, Dialog: Box, Alert: Box } }, registerContribution: value => { contribution = value; } });
  assert.equal(contribution.slot, "plugin.statistics");
  return contribution.component;
}

test("Douban fetches its own API, paginates and handles failed posters", async () => {
  const paths = [];
  const page = { items: [{ id: 1, title: "作品一", poster: "https://img9.doubanio.com/poster.jpg", media_label: "电影", board: "热门综艺", rating: 8.6, subscribed_at: "invalid" }], total: 9, movie_count: 4, tv_count: 5, board_count: 2, page: 1, pages: 2 };
  let configured = false;
  const wrapper = mount(component(async path => { paths.push(path); return { ...page, page: paths.length === 1 ? 1 : 2 }; }), { props: { context: { close() {}, configure: () => { configured = true; } } } });
  await flushPromises();
  assert.deepEqual(wrapper.findAll(".douban-statistics__metrics dd").map(item => item.text()), ["9 条", "4 条", "5 条", "2 个"]);
  assert.match(wrapper.get("img").attributes("src"), /^\/explore\/image-proxy\?source_key=douban/);
  await wrapper.get("img").trigger("error");
  assert.match(wrapper.get(".douban-subscription").text(), /无海报/);
  assert.match(wrapper.get(".douban-subscription").text(), /豆瓣评分 8.6/);
  assert.match(wrapper.get(".douban-subscription").text(), /未知时间/);
  await wrapper.findAll("button").find(button => button.text() === "下一页").trigger("click");
  await flushPromises();
  assert.deepEqual(paths, ["/plugins/douban-hot/api/statistics?page=1", "/plugins/douban-hot/api/statistics?page=2"]);
  assert.equal(wrapper.findAll("button").find(button => button.text() === "下一页").element.disabled, true);
  await wrapper.get('[aria-label="配置豆瓣榜单"]').trigger("click");
  assert.equal(configured, true);
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
