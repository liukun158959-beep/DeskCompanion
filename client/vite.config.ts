import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

// 两页：index.html 宠物窗（vanilla），client.html 主客户端（React）
export default defineConfig({
  clearScreen: false,
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    // 调试页直接读技能原文，避免再抄一份对照表。
    fs: {
      allow: [resolve(__dirname, "..")],
    },
  },
  build: {
    target: "esnext",
    outDir: "dist",
    rollupOptions: {
      input: {
        pet: resolve(__dirname, "index.html"),
        client: resolve(__dirname, "client.html"),
      },
    },
  },
});
