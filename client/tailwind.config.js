import reendPreset from "reend-components/tailwind";

/** @type {import('tailwindcss').Config} */
export default {
  presets: [reendPreset],
  content: [
    "./index.html",
    "./client.html",
    "./src/**/*.{ts,tsx}",
    "./node_modules/reend-components/dist/**/*.{js,mjs}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Segoe UI", "Microsoft YaHei", "Noto Sans SC", "sans-serif"],
      },
    },
  },
};
