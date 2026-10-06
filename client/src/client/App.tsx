import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Button, Card, CardBody, GlitchText, Input } from "reend-components";
import { BoardPane, shouldReloadBoard, type BoardPayload } from "./board";
import {
  BOARD_FIXTURE,
  BOARD_NOW,
  DEBUG_FIXTURE,
  MAA_IDLE_FIXTURE,
  MAA_LOG_FIXTURE,
  MAA_SKILL_RAW,
  STATUS_FIXTURE,
  debugPane,
  debugRequested,
  installDeskDebug,
} from "./debug";
import { columnItems, MaaPane, type LogPayload, type MaaSnap } from "./maa";
import { matchRules, parseRules, type Analysis, type MaaRule } from "./maa-rules";
import { loadingStatuses, statusError, statusFromPayload, STATUS_KINDS, type StatusKind, type StatusView } from "./status";
import { Markdown } from "./Markdown";
import { DEFAULT_SAMPLING, samplingFromInputs, EFFORTS, type Sampling } from "./sampling";
import {
  backendInfo,
  rpc,
  streamChat,
  type BackendInfo,
  type ChatItem,
  type SessionItem,
} from "./api";

type Pane = "chat" | "board" | "maa";

const debugKind = debugPane();

type Thread = {
  sessionId: string;
  sessions: SessionItem[];
  items: ChatItem[];
};

export function App() {
  const [dark, setDark] = useState(true);
  const [pane, setPane] = useState<Pane>(debugKind === "maa" ? "maa" : debugKind === "board" ? "board" : "chat");
  const [info, setInfo] = useState<BackendInfo | null>(null);
  const [thread, setThread] = useState<Thread | null>(null);
  const [draft, setDraft] = useState("");
  const [sampling, setSampling] = useState<Sampling>(DEFAULT_SAMPLING);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [board, setBoard] = useState<BoardPayload | null>(debugKind === "board" || debugKind === "maa" ? BOARD_FIXTURE : null);
  const [boardClock, setBoardClock] = useState<string | null>(debugKind === "board" || debugKind === "maa" ? BOARD_NOW : null);
  const [boardLoading, setBoardLoading] = useState(false);
  const [statuses, setStatuses] = useState<StatusView[]>(debugKind === "board" || debugKind === "maa" ? STATUS_FIXTURE : []);
  const [maa, setMaa] = useState<MaaSnap | null>(debugKind === "maa" ? MAA_IDLE_FIXTURE : null);
  const [logs, setLogs] = useState<LogPayload | null>(debugKind === "maa" ? MAA_LOG_FIXTURE : null);
  const logsRef = useRef<LogPayload | null>(debugKind === "maa" ? MAA_LOG_FIXTURE : null);
  const [rules, setRules] = useState<MaaRule[] | null>(debugKind === "maa" ? parseRules(MAA_SKILL_RAW) : null);
  const [rulesError, setRulesError] = useState("");
  const [logError, setLogError] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [maaBusy, setMaaBusy] = useState(false);
  const [maaLoading, setMaaLoading] = useState(false);
  const maaBusyRef = useRef(false);
  const openMaaRef = useRef<() => void>(() => {});
  const analyzeRef = useRef<() => void>(() => {});
  const seedLogsRef = useRef<(next: LogPayload) => void>(() => {});
  const statusGen = useRef(0);
  const boardSeen = useRef(false);
  const boardFetches = useRef(0);
  const [fetchCount, setFetchCount] = useState(0);
  const openBoardRef = useRef<(refresh?: boolean) => void>(() => {});
  const [preview, setPreview] = useState<ChatItem[] | null>(debugRequested() ? DEBUG_FIXTURE : null);
  const scroller = useRef<HTMLDivElement>(null);
  const notesRef = useRef<string[]>([]);
  const thinkingRef = useRef("");
  const debugMode = preview !== null;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.classList.toggle("light", !dark);
  }, [dark]);

  useEffect(() => {
    if (!isTauri()) return;
    let stop = () => {};
    void listen("open-today", () => {
      openBoardRef.current(false);
    }).then((unlisten) => {
      stop = unlisten;
    });
    return () => stop();
  }, []);

  async function loadThread(backend: BackendInfo) {
    const data = await rpc<{
      session_id: string;
      items: ChatItem[];
      sessions: SessionItem[];
    }>(backend, "load_chat_log");
    setThread({
      sessionId: data.session_id,
      sessions: data.sessions,
      items: data.items,
    });
  }

  useEffect(() => {
    installDeskDebug({
      seed: setPreview,
      seedBoard: (payload, nowIso) => {
        setPane("board");
        setBoard(payload);
        setBoardClock(nowIso);
      },
      seedStatus: (raw) => {
        setPane("board");
        setStatuses(STATUS_KINDS.map((kind) => statusFromPayload(kind, raw[kind])));
      },
      openBoard: (refresh = false) => openBoardRef.current(refresh),
      requestToday: () => openBoardRef.current(false),
      openMaa: () => openMaaRef.current(),
      analyzeMaa: () => analyzeRef.current(),
      seedMaaLogs: (next) => seedLogsRef.current(next),
      shouldReloadBoard,
      setSampling: (effort, temperature, topP) => {
        setSampling(samplingFromInputs(effort, temperature, topP));
      },
    });
    if (debugPane()) return;
    backendInfo()
      .then(async (backend) => {
        setInfo(backend);
        await loadThread(backend);
      })
      .catch((err: unknown) => setError(String(err)));
  }, []);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [thread?.items, status]);

  async function newSession() {
    if (!info || busy) return;
    setError("");
    const created = await rpc<{ session_id: string }>(info, "new_chat_session");
    if (!created.session_id) return;
    await loadThread(info);
  }

  async function openSession(sessionId: string) {
    if (!info || busy || sessionId === thread?.sessionId) return;
    setError("");
    await rpc(info, "switch_chat_session", { session_id: sessionId });
    await loadThread(info);
  }

  function send() {
    const text = draft.trim();
    if (!info || !thread || !text || busy) return;
    setDraft("");
    setBusy(true);
    setError("");
    setStatus("凯尔希思考中…");
    notesRef.current = [];
    thinkingRef.current = "";
    const sent = sampling;
    setThread({
      ...thread,
      items: [...thread.items, { role: "user", text }, { role: "pet", text: "" }],
    });
    streamChat(info, text, sent, {
      onStatus: (line) => {
        if (!line) return;
        setStatus("");
        notesRef.current = [...notesRef.current, line];
        const notes = notesRef.current;
        setThread((cur) => {
          if (!cur) return cur;
          const items = cur.items.slice();
          const last = items[items.length - 1];
          if (!last || last.role !== "pet") return cur;
          items[items.length - 1] = { ...last, notes };
          return { ...cur, items };
        });
      },
      onThink: (piece) => {
        setStatus("");
        thinkingRef.current += piece;
        const thinking = thinkingRef.current;
        setThread((cur) => {
          if (!cur) return cur;
          const items = cur.items.slice();
          const last = items[items.length - 1];
          if (!last || last.role !== "pet") return cur;
          items[items.length - 1] = { ...last, thinking };
          return { ...cur, items };
        });
      },
      onToken: (piece) => {
        setStatus("");
        setThread((cur) => {
          if (!cur) return cur;
          const items = cur.items.slice();
          const last = items[items.length - 1];
          if (last && last.role === "pet") {
            items[items.length - 1] = { ...last, text: last.text + piece };
          }
          return { ...cur, items };
        });
      },
      onDone: async () => {
        const notes = notesRef.current.slice();
        const thinking = thinkingRef.current;
        setStatus("");
        setBusy(false);
        await loadThread(info);
        if (!notes.length && !thinking) return;
        setThread((cur) => {
          if (!cur) return cur;
          const items = cur.items.slice();
          for (let i = items.length - 1; i >= 0; i -= 1) {
            if (items[i].role === "pet") {
              items[i] = {
                ...items[i],
                notes: notes.length ? notes : items[i].notes,
                thinking: thinking || items[i].thinking,
              };
              break;
            }
          }
          return { ...cur, items };
        });
      },
      onError: (message) => {
        setStatus("");
        setBusy(false);
        setError(message);
      },
    });
  }

  function loadStatuses(backend: BackendInfo) {
    const mine = statusGen.current + 1;
    statusGen.current = mine;
    setStatuses(loadingStatuses());
    const methods: Record<StatusKind, string> = {
      feishu: "load_feishu",
      github: "load_github",
      maa: "load_maa",
      skland: "load_skland",
    };
    for (const kind of STATUS_KINDS) {
      rpc<unknown>(backend, methods[kind])
        .then((data) => {
          if (statusGen.current !== mine) return;
          setStatuses((cur) => cur.map((card) => (card.kind === kind ? statusFromPayload(kind, data) : card)));
        })
        .catch((err: unknown) => {
          if (statusGen.current !== mine) return;
          setStatuses((cur) => cur.map((card) => (card.kind === kind ? statusError(kind, String(err)) : card)));
        });
    }
  }

  function openBoard(refresh = false) {
    setPane("board");
    if (!shouldReloadBoard({ refresh, seen: boardSeen.current, debug: boardClock !== null })) return;
    boardSeen.current = true;
    if (!info) {
      setBoard({ ok: false, error: "还没有连上本地后端。恢复：重启客户端。" });
      setStatuses(STATUS_KINDS.map((kind) => statusError(kind, "还没有连上本地后端。恢复：重启客户端。")));
      return;
    }
    boardFetches.current += 1;
    setFetchCount(boardFetches.current);
    setBoardLoading(true);
    loadStatuses(info);
    void loadBoardSnapshot(refresh);
  }

  async function loadBoardSnapshot(refresh: boolean) {
    if (!info) return;
    try {
      const data = await rpc<BoardPayload>(info, "load_board", refresh ? { refresh: true } : {});
      setBoardClock(null);
      setBoard(data);
    } catch (err) {
      setBoard({ ok: false, error: String(err) });
    } finally {
      setBoardLoading(false);
    }
  }

  function rememberMaa(snap: MaaSnap) {
    setMaa(snap);
    setStatuses((cur) => cur.map((card) => (card.kind === "maa" ? statusFromPayload("maa", snap) : card)));
  }

  async function pullMaa(backend: BackendInfo) {
    const snap = await rpc<MaaSnap>(backend, "load_maa");
    const nextLogs = await rpc<LogPayload>(backend, "load_log_errors");
    if (nextLogs.ok === false) {
      setLogError(nextLogs.error || "读取日志失败。");
    } else {
      setLogError("");
      logsRef.current = nextLogs;
      setLogs(nextLogs);
    }
    rememberMaa(snap);
  }

  async function openMaa() {
    setPane("maa");
    setAnalysis(null);
    if (boardClock !== null) {
      try {
        setRules(parseRules(MAA_SKILL_RAW));
        setRulesError("");
      } catch (err) {
        setRules(null);
        setRulesError(String(err));
      }
      logsRef.current = MAA_LOG_FIXTURE;
      setLogs(MAA_LOG_FIXTURE);
      setLogError("");
      setMaa((cur) => cur || MAA_IDLE_FIXTURE);
      return;
    }
    if (!info) {
      setLogError("还没有连上本地后端。恢复：重启客户端。");
      return;
    }
    setMaaLoading(true);
    try {
      const skillPack = await rpc<{ items?: { id: string; body: string }[] }>(info, "load_skills");
      const body = skillPack.items?.find((item) => item.id === "maa-log-analysis")?.body;
      if (!body) {
        throw new Error("没有 maa-log-analysis。恢复：检查 skills/maa-log-analysis/SKILL.md。");
      }
      setRules(parseRules(body));
      setRulesError("");
      await pullMaa(info);
    } catch (err) {
      setRules(null);
      setRulesError(String(err));
    } finally {
      setMaaLoading(false);
    }
  }

  async function startDaily() {
    if (maaBusyRef.current) return;
    if (boardClock !== null) {
      rememberMaa({
        ok: true,
        status: "daily",
        running: true,
        message: "正在确认游戏窗并让 MAA 清日常…",
        current_task: "理智作战",
        task_error: "",
      });
      return;
    }
    if (!info) {
      rememberMaa({ ok: false, status: "error", running: false, message: "还没有连上本地后端。恢复：重启客户端。" });
      return;
    }
    maaBusyRef.current = true;
    setMaaBusy(true);
    try {
      const result = await rpc<MaaSnap>(info, "maa_start_daily");
      if (result.ok === false) {
        rememberMaa({
          ok: false,
          status: "error",
          running: false,
          message: result.error || "开始清日常失败。",
          error: result.error,
        });
        return;
      }
      rememberMaa({
        ok: true,
        status: "daily",
        running: true,
        message: result.message || "",
        current_task: maa?.current_task || "",
        task_error: maa?.task_error || "",
      });
      await pullMaa(info);
    } catch (err) {
      rememberMaa({ ok: false, status: "error", running: false, message: String(err) });
    } finally {
      maaBusyRef.current = false;
      setMaaBusy(false);
    }
  }

  async function stopDaily() {
    if (maaBusyRef.current) return;
    if (boardClock !== null) {
      rememberMaa({
        ok: true,
        status: "idle",
        running: false,
        message: "已请求停止。",
        current_task: "",
        task_error: "",
      });
      return;
    }
    if (!info) {
      rememberMaa({ ok: false, status: "error", running: false, message: "还没有连上本地后端。恢复：重启客户端。" });
      return;
    }
    maaBusyRef.current = true;
    setMaaBusy(true);
    try {
      const result = await rpc<MaaSnap>(info, "maa_stop");
      if (result.ok === false) {
        rememberMaa({
          ok: false,
          status: "error",
          running: maa?.running === true,
          message: result.error || "停止失败。",
          error: result.error,
        });
        return;
      }
      rememberMaa({
        ...(maa || {}),
        ok: true,
        message: result.message || "已请求停止。",
      });
      await pullMaa(info);
    } catch (err) {
      rememberMaa({ ...(maa || {}), ok: false, status: "error", message: String(err) });
    } finally {
      maaBusyRef.current = false;
      setMaaBusy(false);
    }
  }

  function analyzeLogs() {
    if (rulesError || !rules) {
      setAnalysis({
        kind: "bad",
        message: rulesError || "还没有技能表。恢复：检查 skills/maa-log-analysis/SKILL.md。",
      });
      return;
    }
    if (logError) {
      setAnalysis({ kind: "bad", message: logError });
      return;
    }
    setAnalysis(matchRules(columnItems(logsRef.current), rules));
  }

  openMaaRef.current = () => {
    void openMaa();
  };
  analyzeRef.current = analyzeLogs;
  seedLogsRef.current = (next) => {
    logsRef.current = next;
    setLogs(next);
    setLogError("");
    setAnalysis(null);
  };
  openBoardRef.current = openBoard;

  useEffect(() => {
    if (pane !== "maa" || boardClock !== null || !info || maa?.running !== true) return;
    const timer = window.setInterval(() => {
      if (maaBusyRef.current) return;
      void pullMaa(info).catch((err: unknown) => setLogError(String(err)));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [pane, boardClock, info, maa?.running]);

  return (
    <div className="relative flex h-full overflow-hidden bg-background text-foreground" data-pane={pane}>
      <div className="desk-bg" data-bg-motion aria-hidden="true" />
      <aside className="relative z-10 corner-brackets flex w-64 shrink-0 flex-col border-r border-border bg-card/80 backdrop-blur-md">
        <div className="px-4 py-5">
          <div className="ef-overline">DESK COMPANION</div>
          <GlitchText className="mt-1 block text-lg font-semibold text-primary" intensity="low">
            凯尔希
          </GlitchText>
        </div>
        <nav className="flex gap-2 px-3">
          <NavButton active={pane === "chat"} onClick={() => setPane("chat")} label="对话" />
          <NavButton active={pane === "board"} onClick={() => void openBoard()} label="看板" />
        </nav>
        <div className="mt-4 flex items-center justify-between px-4 text-xs text-muted-foreground">
          <span>会话</span>
          <Button type="button" variant="ghost" size="sm" onClick={() => void newSession()}>
            新对话
          </Button>
        </div>
        <div className="mt-2 flex-1 overflow-y-auto px-2">
          {(thread?.sessions || []).map((session) => (
            <button
              key={session.id}
              type="button"
              onClick={() => void openSession(session.id)}
              className={`mb-1 w-full px-3 py-2 text-left text-sm transition-colors duration-200 ${
                session.id === thread?.sessionId
                  ? "bg-primary/15 text-primary"
                  : "text-muted-foreground hover:bg-secondary"
              }`}
            >
              <div className="truncate">{session.title || "未命名对话"}</div>
            </button>
          ))}
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="mx-3 mt-3"
          onClick={() => {
            invoke("set_pet_visible", { visible: true }).catch((err: unknown) => {
              setError(`唤出桌宠失败：${String(err)}。恢复：重启客户端。`);
            });
          }}
        >
          唤出桌宠
        </Button>
        <Button type="button" variant="ghost" size="sm" className="m-3" onClick={() => setDark((v) => !v)}>
          {dark ? "浅色" : "深色"}
        </Button>
      </aside>
      <main className="relative z-10 flex min-w-0 flex-1 flex-col">
        <AnimatePresence mode="wait">
          {pane === "chat" ? (
            <motion.section
              key="chat"
              className="flex min-h-0 flex-1 flex-col"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
            >
              <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto px-8 py-6">
                {debugMode ? (
                  <div className="text-xs text-muted-foreground">调试样本，未连接后端</div>
                ) : null}
                {(preview || thread?.items || []).map((item, idx, all) => (
                  <Bubble
                    key={`${item.ts || idx}-${idx}`}
                    role={item.role}
                    text={item.text}
                    notes={item.notes}
                    thinking={item.thinking}
                    live={busy && !preview && idx === all.length - 1 && item.role === "pet"}
                  />
                ))}
                {status ? <div className="text-sm italic text-muted-foreground">{status}</div> : null}
                {error ? <div className="text-sm text-destructive">{error}</div> : null}
              </div>
              <div className="border-t border-border px-6 py-4">
                <SamplingBar value={sampling} onChange={setSampling} />
                <form
                  className="flex gap-2"
                  onSubmit={(ev) => {
                    ev.preventDefault();
                    send();
                  }}
                >
                <Input
                  value={draft}
                  onChange={(ev) => setDraft(ev.target.value)}
                  placeholder="问今天干什么，或直接跟凯尔希说"
                  className="flex-1"
                />
                <Button type="submit" variant="primary" disabled={busy}>
                  发送
                </Button>
                </form>
              </div>
            </motion.section>
          ) : pane === "maa" ? (
            <motion.section
              key="maa"
              className="flex-1 overflow-y-auto px-8 py-6"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
            >
              <MaaPane
                snap={maa}
                logs={logs}
                logError={logError}
                rulesError={rulesError}
                analysis={analysis}
                busy={maaBusy}
                loading={maaLoading}
                debug={boardClock !== null}
                onBack={() => setPane("board")}
                onStart={() => void startDaily()}
                onStop={() => void stopDaily()}
                onAnalyze={analyzeLogs}
              />
            </motion.section>
          ) : (
            <motion.section
              key="board"
              className="flex-1 overflow-y-auto px-8 py-6"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
            >
              <BoardPane
                data={board}
                nowIso={boardClock}
                loading={boardLoading}
                debug={boardClock !== null}
                onRefresh={() => void openBoard(true)}
                statuses={statuses}
                fetches={fetchCount}
                onOpenMaa={() => void openMaa()}
              />
            </motion.section>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}

function NavButton(props: { active: boolean; label: string; onClick: () => void }) {
  return (
    <Button type="button" size="sm" variant={props.active ? "primary" : "ghost"} onClick={props.onClick}>
      {props.label}
    </Button>
  );
}

function Bubble(props: { role: string; text: string; notes?: string[]; thinking?: string; live?: boolean }) {
  const mine = props.role === "user";
  let body: ReactNode = "…";
  if (props.text) {
    body = mine ? props.text : <Markdown text={props.text} />;
  }
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`} data-bubble data-role={props.role}>
      <Card className={`max-w-[70%] text-sm leading-6 ${mine ? "whitespace-pre-wrap" : ""}`} selected={mine}>
        <CardBody>
        {!mine && props.thinking ? <ThinkCard text={props.thinking} live={!!props.live} /> : null}
        {!mine && props.notes && props.notes.length > 0 ? (
          <ToolCard notes={props.notes} live={!!props.live} />
        ) : null}
        {body}
        </CardBody>
      </Card>
    </div>
  );
}

function ThinkCard(props: { text: string; live: boolean }) {
  const [opened, setOpened] = useState(props.live);
  useEffect(() => {
    setOpened(props.live);
  }, [props.live]);
  return (
    <details
      className="tool-card"
      open={opened}
      data-thinking=""
      data-thinking-live={props.live ? "1" : "0"}
      data-thinking-body={props.text}
      onToggle={(ev) => {
        if (props.live) return;
        setOpened(ev.currentTarget.open);
      }}
    >
      <summary>思考</summary>
      <p className="whitespace-pre-wrap">{props.text}</p>
    </details>
  );
}

function SamplingBar(props: { value: Sampling; onChange: (next: Sampling) => void }) {
  return (
    <div
      className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground"
      data-sampling=""
      data-sampling-effort={props.value.reasoning_effort}
      data-sampling-temperature={props.value.temperature.toFixed(1)}
      data-sampling-top-p={props.value.top_p.toFixed(2)}
    >
      <span>思考</span>
      {EFFORTS.map((effort) => (
        <span key={effort} data-effort={effort} data-selected={props.value.reasoning_effort === effort ? "1" : "0"}>
          <Button
            type="button"
            size="sm"
            variant={props.value.reasoning_effort === effort ? "primary" : "ghost"}
            onClick={() => props.onChange({ ...props.value, reasoning_effort: effort })}
          >
            {effort}
          </Button>
        </span>
      ))}
      <label className="flex items-center gap-2">
        温度
        <input
          className="w-24"
          type="range"
          min={0}
          max={1}
          step={0.1}
          value={props.value.temperature}
          data-temperature=""
          onChange={(ev) => props.onChange({ ...props.value, temperature: Number(ev.target.value) })}
        />
        <span data-temperature-value="">{props.value.temperature.toFixed(1)}</span>
      </label>
      <label className="flex items-center gap-2">
        top_p
        <input
          className="w-24"
          type="range"
          min={0.01}
          max={1}
          step={0.01}
          value={props.value.top_p}
          data-top-p=""
          onChange={(ev) => props.onChange({ ...props.value, top_p: Number(ev.target.value) })}
        />
        <span data-top-p-value="">{props.value.top_p.toFixed(2)}</span>
      </label>
    </div>
  );
}

function ToolCard(props: { notes: string[]; live: boolean }) {
  const title = props.live
    ? props.notes[props.notes.length - 1]
    : props.notes.length === 1
      ? props.notes[0]
      : `${props.notes.length} 次工具调用`;
  return (
    <details className="tool-card" open={props.live || undefined}>
      <summary>{title}</summary>
      <ul>
        {props.notes.map((line, idx) => (
          <li key={`${idx}-${line}`}>{line}</li>
        ))}
      </ul>
    </details>
  );
}
