import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        syn: {
          bg: "#0a0a0f",
          surface: "#12121a",
          border: "#1e1e2e",
          accent: "#00b4d8",
          success: "#22c55e",
          warning: "#f59e0b",
          danger: "#ef4444",
          text: "#e2e8f0",
          muted: "#64748b",
        },
      },
    },
  },
  plugins: [],
};

export default config;
