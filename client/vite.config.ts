import { defineConfig } from "vite";

// Tauri 期望固定端口的开发服务器
export default defineConfig({
  clearScreen: false,
  server: {
    port: 5180,
    strictPort: true,
  },
  build: {
    target: "esnext",
    outDir: "dist",
  },
});
