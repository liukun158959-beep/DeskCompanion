import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Button, Card, CardBody, GlitchText, Input } from "reend-components";
import { BoardPane, shouldReloadBoard, type BoardPayload } from "./board";
import { BOARD_FIXTURE, BOARD_NOW, DEBUG_FIXTURE, STATUS_FIXTURE, debugPane, debugRequested, installDeskDebug } from "./debug";
import { loadingStatuses, statusError, statusFromPayload, STATUS_KINDS, type StatusKind, type StatusView } from "./status";
import { Markdown } from "./Markdown";
import {
  backendInfo,
  rpc,
  streamChat,
  type BackendInfo,
  type ChatItem,
  type SessionItem,
} from "./api";

type Pane = "chat" | "board";

type Thread = {
  sessionId: string;
  sessions: SessionItem[];
  items: ChatItem[];
};

export function App() {
  const [dark, setDark] = useState(true);
  const [pane, setPane] = useState<Pane>(debugPane() === "board" ? "board" : "chat");
  const [info, setInfo] = useState<BackendInfo | null>(null);
  const [thread, setThread] = useState<Thread | null>(null);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [board, setBoard] = useState<BoardPayload | null>(debugPane() === "board" ? BOARD_FIXTURE : null);
  const [boardClock, setBoardClock] = useState<string | null>(debugPane() === "board" ? BOARD_NOW : null);
  const [boardLoading, setBoardLoading] = useState(false);
  const [statuses, setStatuses] = useState<StatusView[]>(debugPane() === "board" ? STATUS_FIXTURE : []);
  const statusGen = useRef(0);
  const boardSeen = useRef(false);
  const boardFetches = useRef(0);
  const [fetchCount, setFetchCount] = useState(0);
  const openBoardRef = useRef<(refresh?: boolean) => void>(() => {});
  const [preview, setPreview] = useState<ChatItem[] | null>(debugRequested() ? DEBUG_FIXTURE : null);
  const scroller = useRef<HTMLDivElement>(null);
  const notesRef = useRef<string[]>([]);
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
      shouldReloadBoard,
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
    setThread({
      ...thread,
      items: [...thread.items, { role: "user", text }, { role: "pet", text: "" }],
    });
    streamChat(info, text, {
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
        setStatus("");
        setBusy(false);
        await loadThread(info);
        if (!notes.length) return;
        setThread((cur) => {
          if (!cur) return cur;
          const items = cur.items.slice();
          for (let i = items.length - 1; i >= 0; i -= 1) {
            if (items[i].role === "pet") {
              items[i] = { ...items[i], notes };
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

  openBoardRef.current = openBoard;

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
                    live={busy && !preview && idx === all.length - 1 && item.role === "pet"}
                  />
                ))}
                {status ? <div className="text-sm italic text-muted-foreground">{status}</div> : null}
                {error ? <div className="text-sm text-destructive">{error}</div> : null}
              </div>
              <form
                className="flex gap-2 border-t border-border px-6 py-4"
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

function Bubble(props: { role: string; text: string; notes?: string[]; live?: boolean }) {
  const mine = props.role === "user";
  let body: ReactNode = "…";
  if (props.text) {
    body = mine ? props.text : <Markdown text={props.text} />;
  }
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`} data-bubble data-role={props.role}>
      <Card className={`max-w-[70%] text-sm leading-6 ${mine ? "whitespace-pre-wrap" : ""}`} selected={mine}>
        <CardBody>
        {!mine && props.notes && props.notes.length > 0 ? (
          <ToolCard notes={props.notes} live={!!props.live} />
        ) : null}
        {body}
        </CardBody>
      </Card>
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
