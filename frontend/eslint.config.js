import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import jsxA11y from "eslint-plugin-jsx-a11y";
import prettier from "eslint-config-prettier";

export default tseslint.config(
  // Ignore generated/build artifacts and Vite/Vitest config files (not in tsconfig)
  {
    ignores: [
      "dist",
      "docs",
      "coverage",
      "node_modules",
      "styled-system",
      "panda.config.ts",
      "vite.config.ts",
      "vitest.config.ts",
      "playwright.config.ts",
      "e2e",
      "src/api/openapi.d.ts",
    ],
  },

  // Base JS recommended rules
  js.configs.recommended,

  // TypeScript strict type-checked + stylistic rules (applied globally, but
  // parserOptions with projectService only makes sense for TS files; JS config
  // files are excluded below via disableTypeChecked)
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,

  // Prettier disables formatting rules that conflict with Prettier — must be LAST
  prettier,

  // Enable type information for all files linted (TS/TSX source)
  {
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },

  {
    // Apply plugin rules to all TS/TSX source files
    files: ["src/**/*.{ts,tsx}"],
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      // React Hooks rules (spread recommended, then override noisy rules)
      ...reactHooks.configs.recommended.rules,
      // set-state-in-effect: the "fire an async loader from useEffect" pattern is
      // legitimate for fetch-on-mount; downgrade from error to warn.
      "react-hooks/set-state-in-effect": "warn",

      // Vite HMR — warn instead of error to allow non-component exports
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],

      // TypeScript-specific tweaks
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],

      // Async event handlers on DOM elements are common in React; downgrade to warn
      "@typescript-eslint/no-misused-promises": [
        "warn",
        { checksVoidReturn: { attributes: false } },
      ],

      // Floating promises in effects are intentional (fire-and-forget via void)
      "@typescript-eslint/no-floating-promises": "warn",

      // prefer-nullish-coalescing fires on `|| ""` patterns that are intentional
      // string-default idioms; too noisy for this codebase with strictNullChecks
      "@typescript-eslint/prefer-nullish-coalescing": "off",

      // consistent-type-imports is already enforced by verbatimModuleSyntax in TS
      "@typescript-eslint/consistent-type-imports": "off",

      // A11y — recommended rules from jsx-a11y
      ...jsxA11y.configs.recommended.rules,

      // Ban inline style={{}} — use Panda css() or className instead.
      // Migration complete: rule is now "error" to block regressions.
      // The single exception (ConfidenceBar dynamic width) is disabled inline.
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='style']",
          message:
            "Avoid inline style prop; use Panda css() or a className recipe instead.",
        },
      ],
    },
  },

  // Disable type-checked rules for JS/CJS config files that are not part of the TS project
  {
    files: ["*.js", "*.mjs", "*.cjs"],
    ...tseslint.configs.disableTypeChecked,
    rules: {
      ...tseslint.configs.disableTypeChecked.rules,
      // CJS config files use `module` global
      "no-undef": "off",
    },
  },
);
