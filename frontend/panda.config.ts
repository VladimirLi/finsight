import { defineConfig } from "@pandacss/dev";

export default defineConfig({
  // Strict tokens: reject any color/spacing/etc not in the theme
  strictTokens: true,
  strictPropertyValues: true,

  // No CSS reset — we handle our own in index.css
  preflight: false,

  // JSX framework
  jsxFramework: "react",

  // Where to scan for css() / cva() calls
  include: ["./src/**/*.{ts,tsx}"],
  exclude: [],

  // Output directory — added to .gitignore
  outdir: "styled-system",

  theme: {
    // ------------------------------------------------------------------ tokens
    tokens: {
      colors: {
        // Neutral grays
        neutral: {
          50: { value: "#f8f9fb" },
          100: { value: "#f3f4f6" },
          200: { value: "#e5e7eb" },
          300: { value: "#d1d5db" },
          400: { value: "#9ca3af" },
          500: { value: "#6b7280" },
          600: { value: "#4b5563" },
          700: { value: "#374151" },
          800: { value: "#1f2937" },
          900: { value: "#1a1f2e" },
        },
        // Brand / primary (blue)
        primary: {
          50: { value: "#eff6ff" },
          300: { value: "#93c5fd" },
          500: { value: "#3b82f6" },
          600: { value: "#2563eb" },
          700: { value: "#1d4ed8" },
          800: { value: "#1e40af" },
        },
        // Semantic — success (green)
        success: {
          50: { value: "#f0fdf4" },
          200: { value: "#bbf7d0" },
          600: { value: "#16a34a" },
          700: { value: "#15803d" },
        },
        // Semantic — warning (amber)
        warning: {
          50: { value: "#fffbeb" },
          200: { value: "#fde68a" },
          600: { value: "#d97706" },
          700: { value: "#b45309" },
        },
        // Semantic — danger (red)
        danger: {
          50: { value: "#fef2f2" },
          200: { value: "#fecaca" },
          600: { value: "#dc2626" },
          700: { value: "#b91c1c" },
        },
        // Semantic — info (cyan)
        info: {
          50: { value: "#ecfeff" },
          200: { value: "#a5f3fc" },
          600: { value: "#0891b2" },
          700: { value: "#0e7490" },
        },
        // Solid white / surface
        white: { value: "#ffffff" },
      },

      spacing: {
        "1": { value: "0.25rem" },
        "2": { value: "0.5rem" },
        "3": { value: "0.75rem" },
        "4": { value: "1rem" },
        "5": { value: "1.25rem" },
        "6": { value: "1.5rem" },
        "8": { value: "2rem" },
        "10": { value: "2.5rem" },
        "12": { value: "3rem" },
      },

      radii: {
        sm: { value: "0.25rem" },
        md: { value: "0.5rem" },
        lg: { value: "0.75rem" },
        xl: { value: "1rem" },
        full: { value: "9999px" },
      },

      fontSizes: {
        xs: { value: "0.75rem" },
        sm: { value: "0.875rem" },
        base: { value: "1rem" },
        lg: { value: "1.125rem" },
        xl: { value: "1.25rem" },
        "2xl": { value: "1.5rem" },
        "3xl": { value: "1.875rem" },
      },

      fontWeights: {
        normal: { value: "400" },
        medium: { value: "500" },
        semibold: { value: "600" },
        bold: { value: "700" },
      },

      fonts: {
        sans: {
          value: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
        },
        mono: {
          value:
            "'SF Mono', 'Fira Code', 'Fira Mono', 'Roboto Mono', monospace",
        },
      },

      shadows: {
        sm: { value: "0 1px 2px 0 rgba(0,0,0,0.05)" },
        md: {
          value:
            "0 1px 3px 0 rgba(0,0,0,0.08), 0 1px 2px -1px rgba(0,0,0,0.08)",
        },
        lg: {
          value:
            "0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.07)",
        },
        xl: {
          value:
            "0 10px 15px -3px rgba(0,0,0,0.07), 0 4px 6px -4px rgba(0,0,0,0.07)",
        },
      },
    },

    // --------------------------------------------------------- semantic tokens
    semanticTokens: {
      colors: {
        bg: { value: "{colors.neutral.50}" },
        surface: { value: "{colors.white}" },
        border: { value: "{colors.neutral.200}" },
        borderLight: { value: "{colors.neutral.100}" },

        text: { value: "{colors.neutral.900}" },
        textMuted: { value: "{colors.neutral.500}" },
        textSubtle: { value: "{colors.neutral.400}" },

        brand: { value: "{colors.primary.600}" },
        brandDark: { value: "{colors.primary.700}" },
        brandBg: { value: "{colors.primary.50}" },

        // Identity / ratio status colours
        ok: { value: "{colors.success.600}" },
        okBg: { value: "{colors.success.50}" },
        mismatch: { value: "{colors.danger.600}" },
        mismatchBg: { value: "{colors.danger.50}" },
        unavailable: { value: "{colors.warning.600}" },
        unavailableBg: { value: "{colors.warning.50}" },
        na: { value: "{colors.neutral.400}" },
        naBg: { value: "{colors.neutral.100}" },
      },
    },

    // ---------------------------------------------------------------- recipes
    recipes: {
      // Button recipe
      button: {
        className: "btn",
        description: "Finsight button",
        base: {
          display: "inline-flex",
          alignItems: "center",
          gap: "2",
          border: "1px solid transparent",
          borderRadius: "md",
          fontSize: "sm",
          fontWeight: "medium",
          cursor: "pointer",
          textDecoration: "none",
          whiteSpace: "nowrap",
          transition:
            "background 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s",
          _disabled: { opacity: "0.5", cursor: "not-allowed" },
        },
        variants: {
          variant: {
            primary: {
              background: "brand",
              color: "white",
              borderColor: "brand",
              _hover: { background: "brandDark", borderColor: "brandDark" },
            },
            secondary: {
              background: "surface",
              color: "text",
              borderColor: "border",
              _hover: { background: "bg", borderColor: "textMuted" },
            },
            danger: {
              background: "mismatch",
              color: "white",
              borderColor: "mismatch",
              _hover: { background: "{colors.danger.700}" },
            },
          },
          size: {
            sm: { padding: "1 3", fontSize: "xs" },
            md: { padding: "2 4" },
            lg: { padding: "3 6", fontSize: "base" },
          },
        },
        defaultVariants: {
          variant: "primary",
          size: "md",
        },
      },

      // StatusBadge recipe — document pipeline status
      statusBadge: {
        className: "status-badge",
        description: "Document pipeline status badge",
        base: {
          display: "inline-flex",
          alignItems: "center",
          gap: "1",
          paddingInline: "2",
          paddingBlock: "0.5",
          borderRadius: "full",
          fontSize: "xs",
          fontWeight: "bold",
          textTransform: "uppercase",
          letterSpacing: "0.04em",
        },
        variants: {
          status: {
            uploaded: { background: "naBg", color: "na" },
            parsing: { background: "brandBg", color: "brand" },
            extracting: { background: "brandBg", color: "brand" },
            needs_review: { background: "unavailableBg", color: "unavailable" },
            ready: { background: "okBg", color: "ok" },
            failed: { background: "mismatchBg", color: "mismatch" },
          },
        },
        defaultVariants: {
          status: "uploaded",
        },
      },

      // RatioCard / identity badge
      identityBadge: {
        className: "identity-badge",
        description: "Accounting identity check status badge",
        base: {
          display: "inline-flex",
          alignItems: "center",
          gap: "1",
          paddingInline: "2",
          paddingBlock: "0.5",
          borderRadius: "full",
          fontSize: "xs",
          fontWeight: "bold",
          textTransform: "uppercase",
          letterSpacing: "0.04em",
        },
        variants: {
          status: {
            ok: { background: "okBg", color: "ok" },
            mismatch: { background: "mismatchBg", color: "mismatch" },
            unavailable: { background: "unavailableBg", color: "unavailable" },
          },
        },
        defaultVariants: {
          status: "ok",
        },
      },
    },
  },
});
