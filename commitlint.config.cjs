// Commitlint configuration for finsight monorepo.
// Extends the Conventional Commits standard.
// https://commitlint.js.org/reference/configuration.html

/** @type {import('@commitlint/types').UserConfig} */
module.exports = {
  extends: ["@commitlint/config-conventional"],

  rules: {
    // Subject must not end with a period.
    "subject-full-stop": [2, "never", "."],

    // Subject must start with a lowercase letter (conventional style).
    "subject-case": [2, "always", "lower-case"],

    // Limit subject to 100 characters (generous for a monorepo with scope).
    "header-max-length": [2, "always", 100],

    // Allowed scopes — add your own as the project grows.
    "scope-enum": [
      1, // warn only so new scopes don't block contributors immediately
      "always",
      [
        "backend",
        "frontend",
        "api",
        "auth",
        "db",
        "docker",
        "ci",
        "deps",
        "config",
        "docs",
        "release",
      ],
    ],

    // Require a scope when the type is feat or fix (keeps changelog useful).
    "scope-empty": [1, "never"],
  },
};
