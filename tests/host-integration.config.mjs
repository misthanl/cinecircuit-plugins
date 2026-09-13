import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// Plugin-owned integration tests run against the sibling host's actual UI runtime.
const host = createRequire(new URL('../../cinecircuit/frontend/package.json', import.meta.url));
const { defineConfig } = await import(pathToFileURL(host.resolve('vitest/config')).href);
const { default: vue } = await import(pathToFileURL(host.resolve('@vitejs/plugin-vue')).href);

export default defineConfig({
  root: fileURLToPath(new URL('../', import.meta.url)),
  plugins: [vue()],
  resolve: {
    preserveSymlinks: true,
    alias: ['vue', '@vue/test-utils', 'vitest', 'vuetify/components', 'vuetify'].map(name => ({
      find: new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`),
      replacement: name === 'vitest'
        ? join(dirname(host.resolve('vitest/package.json')), 'dist/index.js')
        : name === 'vue'
          ? join(dirname(host.resolve('vue/package.json')), 'dist/vue.esm-bundler.js')
          : host.resolve(name),
    })),
  },
  test: {
    server: { deps: { inline: ['vuetify'] } },
    environment: 'jsdom',
    include: ['tests/*.integration.test.ts'],
    fileParallelism: false,
    maxWorkers: 1,
    pool: 'threads',
  },
});
