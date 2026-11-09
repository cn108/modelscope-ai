module.exports = {
  root: true,
  ignorePatterns: [
    'dist/',
    'node_modules/',
    'e2e/',
    'playwright.config.ts',
    'src/environments/*.ts',
    '**/*.spec.ts',
  ],
  parser: '@typescript-eslint/parser',
  parserOptions: {
    project: './tsconfig.app.json',
    tsconfigRootDir: __dirname,
    sourceType: 'module',
  },
  plugins: ['@typescript-eslint'],
  rules: {
    'no-debugger': 'error',
    'no-duplicate-imports': 'error',
    'no-unused-vars': 'off',
    '@typescript-eslint/no-unused-vars': [
      'error',
      {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
      },
    ],
  },
};
