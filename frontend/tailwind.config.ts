import type { Config } from "tailwindcss";

/**
 * Every colour here is a reference to a CSS custom property declared in `src/styles/tokens.css`,
 * never a literal hex value. That is what makes docs/03 §3.1 the single source of truth: changing a
 * token changes the whole product, and a component cannot quietly invent a shade that was never
 * ruled on.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--bg-canvas)",
        panel: "var(--bg-panel)",
        elevated: "var(--bg-elevated)",
        line: "var(--border)",
        primary: "var(--text-primary)",
        secondary: "var(--text-secondary)",
        muted: "var(--text-muted)",
        positive: "var(--green)",
        negative: "var(--red)",
        warning: "var(--amber)",
        info: "var(--cyan)",
        research: "var(--purple)",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      fontSize: {
        // docs/03 §3.2: headings 20/16/14, body 14, data 13 mono, labels 11 uppercase.
        heading: ["20px", { lineHeight: "1.25", fontWeight: "600" }],
        subheading: ["16px", { lineHeight: "1.3", fontWeight: "600" }],
        card: ["14px", { lineHeight: "1.35", fontWeight: "600" }],
        body: ["14px", { lineHeight: "1.5" }],
        data: ["13px", { lineHeight: "1.4" }],
        label: ["11px", { lineHeight: "1.4", letterSpacing: "0.05em" }],
      },
    },
  },
  plugins: [],
};

export default config;
