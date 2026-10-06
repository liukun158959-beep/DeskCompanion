/// <reference types="vite/client" />
import type { ChatItem } from "./api";
import type { BoardPayload } from "./board";
import type { LogPayload, MaaSnap } from "./maa";
import type { FeishuSnap } from "./feishu";
import { statusFromPayload, type StatusKind, type StatusView } from "./status";
import skillRaw from "../../../skills/maa-log-analysis/SKILL.md?raw";

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
    thinking: "先看今天有没有空，再排这三步。",
  },
];

export type BubbleSnap = {
  role: string;
  tags: string[];
  text: string;
  thinking: string;
  thinkingLive: string;
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

export const STATUS_RAW: Record<StatusKind, unknown> = {
  feishu: { ok: true, logged_in: true, user_name: "博士" },
  github: { ok: false, error: "gh auth login" },
  maa: { ok: true, status: "idle", message: "还没开始。" },
  skland: { ok: true, has_token: false, hint: "还没有森空岛凭证。" },
};

export const STATUS_FIXTURE: StatusView[] = (Object.keys(STATUS_RAW) as StatusKind[]).map((kind) =>
  statusFromPayload(kind, STATUS_RAW[kind]),
);

export const MAA_SKILL_RAW = skillRaw;

export const MAA_IDLE_FIXTURE: MaaSnap = {
  ok: true,
  status: "idle",
  message: "还没开始。",
  running: false,
  current_task: "",
  task_error: "",
};

export const MAA_LOG_FIXTURE: LogPayload = {
  ok: true,
  highlights: [{ time: "15:01:00", title: "任务出错: 仓库识别", text: "任务出错: 仓库识别" }],
  desk: { path: "desk_companion.log", note: "", items: [] },
  maa_gui: {
    path: "gui.log",
    note: "",
    items: [{ time: "15:01:00", title: "任务出错: 仓库识别", text: "任务出错: 仓库识别" }],
  },
  maa_depot: {
    path: "asst.log",
    note: "",
    items: [{ time: "15:01:02", title: "没对上「全部」页签", text: "failed to match DepotAllTab" }],
  },
};

export const MAA_EMPTY_LOG: LogPayload = {
  ok: true,
  highlights: [],
  desk: { path: "desk_companion.log", note: "今日没有出错。", items: [] },
  maa_gui: { path: "gui.log", note: "", items: [] },
  maa_depot: { path: "asst.log", note: "", items: [] },
};

export const MAA_UNKNOWN_LOG: LogPayload = {
  ok: true,
  highlights: [],
  desk: { path: "desk_companion.log", items: [{ title: "崩溃", text: "CRASH 样本，技能表里没有这条。" }] },
  maa_gui: { path: "gui.log", items: [] },
  maa_depot: { path: "asst.log", items: [] },
};

export const FEISHU_LOGGED_OUT: FeishuSnap = {
  ok: true,
  installed: true,
  logged_in: false,
  login_busy: false,
  hint: "请在看板「飞书」页登录。需要日历、待办和云文档权限：lark-cli auth login --domain calendar,task,docs",
};

export const FEISHU_WAITING: FeishuSnap = {
  ok: true,
  installed: true,
  logged_in: false,
  login_busy: true,
};

export const FEISHU_LOGGED_IN: FeishuSnap = {
  ok: true,
  installed: true,
  logged_in: true,
  login_busy: false,
  user_name: "博士",
  has_calendar: true,
  has_task: true,
  has_docs: false,
};

export function debugPane(): "chat" | "board" | "maa" | "feishu" | null {
  if (!import.meta.env.DEV) return null;
  const value = new URLSearchParams(location.search).get("debug");
  if (value === "1" || value === "chat") return "chat";
  if (value === "board") return "board";
  if (value === "maa") return "maa";
  if (value === "feishu") return "feishu";
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

export type StatusSnap = { kind: string; state: string; line: string }[];

export type MaaSnapShot = {
  pane: string;
  running: string;
  message: string;
  task: string;
  startDisabled: boolean;
  stopDisabled: boolean;
  kind: string;
  hits: { source: string; text: string }[];
  fetches: string;
};

export function installDeskDebug(api: {
  seed: (items: ChatItem[]) => void;
  seedBoard: (payload: BoardPayload, nowIso: string) => void;
  seedStatus: (raw: Record<string, unknown>) => void;
  openBoard: (refresh?: boolean) => void;
  requestToday: () => void;
  openMaa: () => void;
  analyzeMaa: () => void;
  seedMaaLogs: (logs: LogPayload) => void;
  openFeishu: () => void;
  seedFeishu: (snap: FeishuSnap) => void;
  shouldReloadBoard: (opts: { refresh: boolean; seen: boolean; debug: boolean }) => boolean;
  setSampling: (effort: string, temperature: number, topP: number) => void;
}): void {
  if (!import.meta.env.DEV) return;
  window.__deskDebug = {
    seed: api.seed,
    seedBoard: api.seedBoard,
    seedStatus: api.seedStatus,
    openBoard: api.openBoard,
    requestToday: api.requestToday,
    openMaa: api.openMaa,
    analyzeMaa: api.analyzeMaa,
    seedMaaLogs: api.seedMaaLogs,
    openFeishu: api.openFeishu,
    seedFeishu: api.seedFeishu,
    shouldReloadBoard: api.shouldReloadBoard,
    setSampling: api.setSampling,
    samplingSnapshot(): { effort: string; temperature: string; topP: string } {
      const row = document.querySelector("[data-sampling]");
      return {
        effort: row?.getAttribute("data-sampling-effort") || "",
        temperature: row?.getAttribute("data-sampling-temperature") || "",
        topP: row?.getAttribute("data-sampling-top-p") || "",
      };
    },
    snapshot(): BubbleSnap[] {
      return [...document.querySelectorAll("[data-bubble]")].map((el) => ({
        role: el.getAttribute("data-role") || "",
        tags: [...el.querySelectorAll("*")].map((node) => node.tagName.toLowerCase()),
        text: (el as HTMLElement).innerText,
        thinking: el.querySelector("[data-thinking]")?.getAttribute("data-thinking-body") || "",
        thinkingLive: el.querySelector("[data-thinking]")?.getAttribute("data-thinking-live") || "",
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
    statusSnapshot(): StatusSnap {
      return [...document.querySelectorAll("[data-status]")].map((el) => ({
        kind: el.getAttribute("data-status") || "",
        state: el.getAttribute("data-state") || "",
        line: (el.querySelector("[data-status-line]") as HTMLElement | null)?.innerText || "",
      }));
    },
    maaSnapshot(): MaaSnapShot {
      const root = document.querySelector("[data-maa]");
      const start = document.querySelector("[data-maa-start]") as HTMLButtonElement | null;
      const stop = document.querySelector("[data-maa-stop]") as HTMLButtonElement | null;
      const board = document.querySelector("[data-board]");
      return {
        pane: document.querySelector("[data-pane]")?.getAttribute("data-pane") || "",
        running: root?.getAttribute("data-maa-running") || "",
        message: (document.querySelector("[data-maa-message]") as HTMLElement | null)?.innerText || "",
        task: (document.querySelector("[data-maa-task]") as HTMLElement | null)?.innerText || "",
        startDisabled: !!start?.disabled,
        stopDisabled: !!stop?.disabled,
        kind: document.querySelector("[data-maa-analysis]")?.getAttribute("data-maa-kind") || "",
        hits: [...document.querySelectorAll("[data-maa-hit]")].map((el) => ({
          source: el.getAttribute("data-source") || "",
          text: (el as HTMLElement).innerText,
        })),
        fetches: board?.getAttribute("data-board-fetches") || "",
      };
    },
    navSnapshot(): { mode: string; sub: string; subs: string[] } {
      const nav = document.querySelector("[data-nav]");
      return {
        mode: nav?.getAttribute("data-nav") || "",
        sub: document.querySelector("[data-sub][data-selected='1']")?.getAttribute("data-sub") || "",
        subs: [...document.querySelectorAll("[data-sub]")].map((el) => el.getAttribute("data-sub") || ""),
      };
    },
    feishuSnapshot(): {
      pane: string;
      logged: string;
      busy: string;
      message: string;
      missing: string[];
      loginDisabled: string;
      hasLogout: boolean;
    } {
      const root = document.querySelector("[data-feishu]");
      return {
        pane: document.querySelector("[data-pane]")?.getAttribute("data-pane") || "",
        logged: root?.getAttribute("data-feishu-logged") || "",
        busy: root?.getAttribute("data-feishu-busy") || "",
        message: (document.querySelector("[data-feishu-message]") as HTMLElement | null)?.innerText || "",
        missing: [...document.querySelectorAll("[data-feishu-missing]")].map((el) => (el as HTMLElement).innerText),
        loginDisabled: document.querySelector("[data-feishu-login]")?.getAttribute("data-feishu-login-disabled") || "",
        hasLogout: !!document.querySelector("[data-feishu-logout]"),
      };
    },
    bgMotion(): { grid: string; particles: string } {
      const layer = document.querySelector("[data-bg-motion]");
      if (!layer) return { grid: "", particles: "" };
      const grid = getComputedStyle(layer, "::before");
      const particles = getComputedStyle(layer, "::after");
      return { grid: grid.animationName, particles: particles.animationName };
    },
  };
}

declare global {
  interface Window {
    __deskDebug?: {
      seed: (items: ChatItem[]) => void;
      seedBoard: (payload: BoardPayload, nowIso: string) => void;
      seedStatus: (raw: Record<string, unknown>) => void;
      openBoard: (refresh?: boolean) => void;
      requestToday: () => void;
      openMaa: () => void;
      analyzeMaa: () => void;
      seedMaaLogs: (logs: LogPayload) => void;
      openFeishu: () => void;
      seedFeishu: (snap: FeishuSnap) => void;
      shouldReloadBoard: (opts: { refresh: boolean; seen: boolean; debug: boolean }) => boolean;
      setSampling: (effort: string, temperature: number, topP: number) => void;
      samplingSnapshot: () => { effort: string; temperature: string; topP: string };
      snapshot: () => BubbleSnap[];
      boardSnapshot: () => BoardSnap;
      statusSnapshot: () => StatusSnap;
      maaSnapshot: () => MaaSnapShot;
      navSnapshot: () => { mode: string; sub: string; subs: string[] };
      feishuSnapshot: () => {
        pane: string;
        logged: string;
        busy: string;
        message: string;
        missing: string[];
        loginDisabled: string;
        hasLogout: boolean;
      };
      bgMotion: () => { grid: string; particles: string };
    };
  }
}
