import vue from "@vitejs/plugin-vue";
import { build } from "vite";
import { execFile } from "node:child_process";
import { readdir, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const sourceRoot = resolve(root, "cinecircuit_plugins");
const outputRoot = resolve(root, ".build", "cinecircuit_plugins");
const runtimeGlobal = "__CINECIRCUIT_PLUGIN_VUE_RUNTIME__";
const runtimeExports = [
  "Fragment", "computed", "createBlock", "createCommentVNode", "createElementBlock",
  "createElementVNode", "createTextVNode", "createVNode", "defineComponent", "h",
  "normalizeClass", "normalizeStyle", "onMounted", "openBlock", "reactive", "ref",
  "renderList", "resolveComponent", "toDisplayString", "unref", "withCtx",
];
const execFileAsync = promisify(execFile);

async function hasVueSource(directory) {
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const path = resolve(directory, item.name);
    if (item.isDirectory() && await hasVueSource(path)) return true;
    if (item.isFile() && item.name.endsWith(".vue")) return true;
  }
  return false;
}

function hostVueRuntime() {
  const id = "\0cinecircuit-host-vue-runtime";
  return {
    name: "cinecircuit-host-vue-runtime",
    enforce: "pre",
    resolveId(source) {
      return source === "vue" ? id : null;
    },
    load(source) {
      if (source !== id) return null;
      const bindings = runtimeExports
        .map(name => `export const ${name} = runtime.${name};`)
        .join("\n");
      return `const runtime = globalThis.${runtimeGlobal};\nif (!runtime) throw new Error("CineCircuit host Vue runtime is unavailable");\n${bindings}\nexport default runtime;`;
    },
  };
}

function inlineCss(pluginId) {
  return {
    name: "cinecircuit-inline-plugin-css",
    generateBundle: {
      order: "post",
      handler(_options, bundle) {
        const css = [];
        for (const [name, item] of Object.entries(bundle)) {
          if (item.type === "asset" && name.endsWith(".css")) {
            css.push(String(item.source));
            delete bundle[name];
          }
        }
        if (!css.length) return;
        const entry = Object.values(bundle).find(item => item.type === "chunk" && item.isEntry);
        if (!entry || entry.type !== "chunk") throw new Error("Plugin frontend entry chunk is missing");
        const stylesheet = JSON.stringify(css.join("\n"));
        const id = JSON.stringify(pluginId);
        entry.code = `if (typeof document !== "undefined") { const id = ${id}; document.querySelector(\`style[data-cinecircuit-plugin-style="\${id}"]\`)?.remove(); const style = document.createElement("style"); style.dataset.cinecircuitPluginStyle = id; style.textContent = ${stylesheet}; document.head.appendChild(style); }\n${entry.code}`;
      },
    },
  };
}

await rm(resolve(root, ".build"), { recursive: true, force: true });
await execFileAsync(process.execPath, [
  resolve(root, "node_modules", "typescript", "bin", "tsc"),
  "-p",
  resolve(root, "tsconfig.build.json"),
], { cwd: root });
const directories = (await readdir(sourceRoot, { withFileTypes: true }))
  .filter(item => item.isDirectory())
  .map(item => item.name)
  .sort();

for (const directory of directories) {
  const entry = resolve(sourceRoot, directory, "frontend.ts");
  if (!await hasVueSource(resolve(sourceRoot, directory))) continue;
  await build({
    configFile: false,
    logLevel: "warn",
    plugins: [hostVueRuntime(), vue(), inlineCss(directory)],
    build: {
      target: "es2022",
      minify: false,
      sourcemap: false,
      outDir: resolve(outputRoot, directory),
      emptyOutDir: true,
      lib: { entry, formats: ["es"], fileName: () => "frontend.js" },
      rollupOptions: {
        treeshake: { propertyReadSideEffects: false },
        output: { inlineDynamicImports: true },
      },
    },
  });
}
