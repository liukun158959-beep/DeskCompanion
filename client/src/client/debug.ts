/// <reference types="vite/client" />
import type { ChatItem } from "./api";

// 仅开发态。浏览器打开 /client.html?debug=1 不连 Tauri、不打模型，直接铺一条样本回复。
// 代理用 window.__deskDebug.snapshot() 读气泡里的标签，确认列表和代码块真的排出来了。

export const DEBUG_FIXTURE: ChatItem[] = [
  { role: "user", text: "用列表写三步，并给一段 Python。**不要解析我**" },
  {
    role: "pet",
    text: [
      "三步：",
      "",
      "1. 打开看板",
      "2. 看日程",
      "3. 再问我",
      "",
      "```python",
      'print("hello")',
      "```",
      "",
      "<script>alert(1)</script>",
      "",
      "见 [说明](https://example.com/help)",
    ].join("\n"),
  },
];

export type BubbleSnap = {
  role: string;
  tags: string[];
  text: string;
};

export function debugRequested(): boolean {
  return import.meta.env.DEV && new URLSearchParams(location.search).get("debug") === "1";
}

export function installDeskDebug(seed: (items: ChatItem[]) => void): void {
  if (!import.meta.env.DEV) return;
  window.__deskDebug = {
    seed,
    snapshot(): BubbleSnap[] {
      return [...document.querySelectorAll("[data-bubble]")].map((el) => ({
        role: el.getAttribute("data-role") || "",
        tags: [...el.querySelectorAll("*")].map((node) => node.tagName.toLowerCase()),
        text: (el as HTMLElement).innerText,
      }));
    },
  };
}

declare global {
  interface Window {
    __deskDebug?: {
      seed: (items: ChatItem[]) => void;
      snapshot: () => BubbleSnap[];
    };
  }
}
