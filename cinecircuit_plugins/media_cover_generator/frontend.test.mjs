import assert from "node:assert/strict";
import { test } from "node:test";
import { install } from "../../.build/cinecircuit_plugins/media_cover_generator/frontend.js";

function harness(request) {
  const mounted = [];
  let registration;
  const vue = {
    defineComponent: (definition) => definition,
    h(type, props, children) {
      const isVNode = props !== null && typeof props === "object"
        && "type" in props && ("props" in props || "children" in props);
      if (arguments.length === 2 && (Array.isArray(props) || typeof props !== "object" || isVNode)) {
        return { type, props: {}, children: props };
      }
      return { type, props: props || {}, children };
    },
    onMounted: (callback) => { mounted.push(callback); },
    ref: (value) => ({ value }),
  };
  install({ vue, request, registerPage: (value) => { registration = value; } });
  assert.equal(registration.pluginId, "emby-cover-generator");
  const render = registration.component.setup();
  return { mounted, render };
}

function descendants(node) {
  if (Array.isArray(node)) return node.flatMap(descendants);
  if (!node || typeof node !== "object") return [];
  const children = Array.isArray(node.children)
    ? node.children.flatMap(descendants)
    : descendants(node.children);
  return [node, ...children];
}

test("cover generator preserves server selection, library toggles and run sequence", async () => {
  const calls = [];
  const request = async (path, init) => {
    calls.push({ path, init });
    if (path.endsWith("/api/inventory")) return {
      servers: [{ id: "server-1", name: "Emby" }], libraries: [],
      config: { cover_style_base: "single", selected_servers: [], include_libraries: [] },
    };
    if (path.includes("/api/libraries?")) return { items: [{ id: "library-1", name: "电影", collection_type: "movies" }] };
    return {};
  };
  const view = harness(request);
  await view.mounted[0]();
  let tree = view.render();
  const serverSelect = descendants(tree).find((node) => node.type === "select");
  await serverSelect.props.onChange({ target: { value: "server-1" } });
  assert.equal(calls.at(-1).path, "/plugins/emby-cover-generator/api/libraries?server_id=server-1");

  tree = view.render();
  const libraryCheckbox = descendants(tree).find((node) => node.type === "input" && node.props.type === "checkbox");
  assert.ok(libraryCheckbox, JSON.stringify(descendants(tree).filter((node) => node.type === "input" || node.type === "select")));
  libraryCheckbox.props.onChange();
  const generateButton = descendants(view.render()).find(
    (node) => node.type === "button" && node.props.class !== "alt" && !Array.isArray(node.props.class),
  );
  assert.ok(generateButton, JSON.stringify(descendants(view.render()).filter((node) => node.type === "button")));
  await generateButton.props.onClick();

  const saveCall = calls.find((call) => call.path === "/plugins/emby-cover-generator");
  assert.equal(saveCall.init.method, "PATCH");
  const saved = JSON.parse(saveCall.init.body).config;
  assert.deepEqual(saved.selected_servers, ["server-1"]);
  assert.deepEqual(saved.include_libraries, ["library-1"]);
  assert.equal(saved.dry_run, false);
  assert.equal(calls.at(-1).path, "/plugins/emby-cover-generator/run");
  assert.equal(calls.at(-1).init.method, "POST");
});
