import tseslint from 'typescript-eslint';
import vueParser from 'vue-eslint-parser';
import js from '@eslint/js';
import vue from 'eslint-plugin-vue';

// Keep function budgets identical to the host while owning this configuration
// and its dependencies in the independently released plugin repository.
const budgets = {
  complexity: ['error', 10],
  'max-lines-per-function': ['error', {
    max: 50, skipBlankLines: true, skipComments: true, IIFEs: true,
  }],
  'max-depth': ['error', 4],
  'max-lines': ['error', { max: 1000, skipBlankLines: true, skipComments: true }],
};

const checkedRules = {
  ...js.configs.recommended.rules,
  ...tseslint.configs.recommended.reduce((rules, config) => ({ ...rules, ...config.rules }), {}),
  ...budgets,
  // Public plugin SDK payloads are intentionally open records; checked by vue-tsc.
  '@typescript-eslint/no-explicit-any': 'off',
};

export default [
  ...vue.configs['flat/essential'],
  {
    files: ['cinecircuit_plugins/**/*.ts'],
    ignores: ['**/*.test.ts', '**/*.d.ts'],
    languageOptions: { parser: tseslint.parser },
    plugins: { '@typescript-eslint': tseslint.plugin },
    rules: checkedRules,
  },
  {
    files: ['cinecircuit_plugins/**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: { parser: tseslint.parser, extraFileExtensions: ['.vue'] },
    },
    plugins: { '@typescript-eslint': tseslint.plugin },
    rules: checkedRules,
  },
];
