import assert from "node:assert/strict";
import { test } from "node:test";
import { install } from "../../.build/cinecircuit_plugins/brush_flow/frontend.js";

function harness(request) {
  const mounted = [];
  let registration;
  const vue = {
    defineComponent: (definition) => definition,
    h(type, props, children) {
      if (arguments.length === 2 && (Array.isArray(props) || typeof props !== "object" || "type" in props)) {
        return { type, props: {}, children: props };
      }
      return { type, props: props || {}, children };
    },
    onMounted: (callback) => { mounted.push(callback); },
    ref: (value) => ({ value }),
  };
  install({ vue, request, registerPage: (value) => { registration = value; } });
  assert.equal(registration.pluginId, "brush-flow");
  const render = registration.component.setup();
  return { mounted, render };
}

function descendants(node) {
  if (!node || typeof node !== "object") return [];
  const children = Array.isArray(node.children)
    ? node.children.flatMap(descendants)
    : descendants(node.children);
  return [node, ...children];
}

function button(root, label) {
  return descendants(root).find((node) => node.type === "button" && node.children === label);
}

test("brush flow preserves inventory, preview and save requests", async () => {
  const calls = [];
  const task = {
    id: "task-1", name: "保种", enabled: true, site_id: "site-1", downloader_id: "downloader-1",
    include: "WEB-DL", exclude: "CAM", min_size: 1, max_size: 20, max_add: 3,
    save_path: "/media", delete_ratio: 2, delete_seed_hours: 48, delete_task: false,
  };
  const request = async (path, init) => {
    calls.push({ path, init });
    if (path.endsWith("/api/inventory")) return {
      sites: [{ id: "site-1", name: "站点一" }],
      downloaders: [{ id: "downloader-1", name: "下载器一" }],
      config: { enabled: true }, tasks: [task],
    };
    if (path.endsWith("/api/preview")) return { count: 1, items: [{ title: "候选资源" }] };
    return {};
  };
  const view = harness(request);
  await view.mounted[0]();
  let tree = view.render();
  assert.match(JSON.stringify(tree), /站点一/);

  await button(tree, "预览选种").props.onClick();
  tree = view.render();
  assert.match(JSON.stringify(tree), /候选资源/);
  assert.equal(calls.at(-1).path, "/plugins/brush-flow/api/preview");
  assert.equal(JSON.parse(calls.at(-1).init.body).task_id, "task-1");

  await button(tree, "保存全部").props.onClick();
  assert.equal(calls.at(-1).path, "/plugins/brush-flow");
  assert.equal(calls.at(-1).init.method, "PATCH");
  assert.deepEqual(JSON.parse(calls.at(-1).init.body).config.tasks, [task]);
});
