import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const host = createRequire(new URL('../../cinecircuit/frontend/package.json', import.meta.url));
const cli = join(dirname(host.resolve('vitest/package.json')), 'vitest.mjs');
const result = spawnSync(process.execPath, [cli, 'run', '--config', fileURLToPath(new URL('./host-integration.config.mjs', import.meta.url))], {
  cwd: fileURLToPath(new URL('../', import.meta.url)),
  stdio: 'inherit',
});
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
