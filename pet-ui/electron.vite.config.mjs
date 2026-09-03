import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import { resolve } from "path";

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
  },
  renderer: {
    publicDir: resolve("public"),
    resolve: {
      alias: {
        "@": resolve("src/renderer/src"),
      },
    },
  },
});
