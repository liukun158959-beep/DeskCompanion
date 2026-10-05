/// <reference types="vite/client" />
import type { ChatItem } from "./api";
import type { BoardPayload } from "./board";

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
    notes: ["在看今天的日程…", "在看未完成的待办…"],
  },
];

export type BubbleSnap = {
  role: string;
  tags: string[];
  text: string;
};

export const BOARD_NOW = "2026-10-05T15:00:00+08:00";

// 日程故意打乱。待办一条在样本时刻之前，一条在之后。
export const BOARD_FIXTURE: BoardPayload = {
  ok: true,
  date: "2026-10-05",
  summary: "样本总结，不是飞书原文。",
  agenda: {
    ok: true,
    items: [
      { summary: "晚间复盘", start: "18:00", end: "18:30" },
      { summary: "全天专注", start: "2026-10-05 全天" },
      { summary: "早会", start: "09:10", end: "09:40" },
    ],
  },
  tasks: {
    ok: true,
    items: [
      { summary: "交周报", due_at: "2026-10-05T10:00:00+08:00" },
      { summary: "看看板", due_at: "2026-10-05T20:00:00+08:00" },
    ],
  },
};

export function debugPane(): "chat" | "board" | null {
  if (!import.meta.env.DEV) return null;
  const value = new URLSearchParams(location.search).get("debug");
  if (value === "1" || value === "chat") return "chat";
  if (value === "board") return "board";
  return null;
}

export function debugRequested(): boolean {
  return debugPane() === "chat";
}

export type BoardSnap = {
  fatal: string;
  times: string[];
  titles: string[];
  tasks: { title: string; when: string; overdue: string }[];
  agendaError: string;
  taskError: string;
};

export function installDeskDebug(api: {
  seed: (items: ChatItem[]) => void;
  seedBoard: (payload: BoardPayload, nowIso: string) => void;
}): void {
  if (!import.meta.env.DEV) return;
  window.__deskDebug = {
    seed: api.seed,
    seedBoard: api.seedBoard,
    snapshot(): BubbleSnap[] {
      return [...document.querySelectorAll("[data-bubble]")].map((el) => ({
        role: el.getAttribute("data-role") || "",
        tags: [...el.querySelectorAll("*")].map((node) => node.tagName.toLowerCase()),
        text: (el as HTMLElement).innerText,
      }));
    },
    boardSnapshot(): BoardSnap {
      const fatal = document.querySelector("[data-board-error]");
      return {
        fatal: fatal ? (fatal as HTMLElement).innerText : "",
        times: [...document.querySelectorAll("[data-time]")].map((el) => (el as HTMLElement).innerText),
        titles: [...document.querySelectorAll("[data-title]")].map((el) => (el as HTMLElement).innerText),
        tasks: [...document.querySelectorAll("[data-task]")].map((el) => ({
          title: (el.querySelector("[data-task-title]") as HTMLElement | null)?.innerText || "",
          when: (el.querySelector("[data-task-when]") as HTMLElement | null)?.innerText || "",
          overdue: el.getAttribute("data-overdue") || "",
        })),
        agendaError: (document.querySelector("[data-agenda-error]") as HTMLElement | null)?.innerText || "",
        taskError: (document.querySelector("[data-task-error]") as HTMLElement | null)?.innerText || "",
      };
    },
  };
}

declare global {
  interface Window {
    __deskDebug?: {
      seed: (items: ChatItem[]) => void;
      seedBoard: (payload: BoardPayload, nowIso: string) => void;
      snapshot: () => BubbleSnap[];
      boardSnapshot: () => BoardSnap;
    };
  }
}
