import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
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
  const [dark, setDark] = useState(false);
  const [pane, setPane] = useState<Pane>("chat");
  const [info, setInfo] = useState<BackendInfo | null>(null);
  const [thread, setThread] = useState<Thread | null>(null);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [boardText, setBoardText] = useState("打开看板页时再拉今日数据。");
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

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
    setThread({
      ...thread,
      items: [...thread.items, { role: "user", text }, { role: "pet", text: "" }],
    });
    streamChat(info, text, {
      onStatus: setStatus,
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
        setStatus("");
        setBusy(false);
        await loadThread(info);
      },
      onError: (message) => {
        setStatus("");
        setBusy(false);
        setError(message);
      },
    });
  }

  async function openBoard() {
    setPane("board");
    if (!info) return;
    setBoardText("正在读取今日看板…");
    try {
      const data = await rpc<Record<string, unknown>>(info, "load_board");
      const summary = typeof data.summary === "string" ? data.summary : "";
      setBoardText(summary || "看板已接通，今日摘要为空。");
    } catch (err) {
      setBoardText(String(err));
    }
  }

  return (
    <div className="flex h-full bg-bg text-ink">
      <aside className="flex w-64 shrink-0 flex-col border-r border-line bg-panel">
        <div className="px-4 py-5">
          <div className="text-xs tracking-widest text-muted">DESK COMPANION</div>
          <div className="mt-1 text-lg font-semibold">凯尔希</div>
        </div>
        <nav className="flex gap-2 px-3">
          <NavButton active={pane === "chat"} onClick={() => setPane("chat")} label="对话" />
          <NavButton active={pane === "board"} onClick={() => void openBoard()} label="看板" />
        </nav>
        <div className="mt-4 flex items-center justify-between px-4 text-xs text-muted">
          <span>会话</span>
          <button type="button" className="text-accent" onClick={() => void newSession()}>
            新对话
          </button>
        </div>
        <div className="mt-2 flex-1 overflow-y-auto px-2">
          {(thread?.sessions || []).map((session) => (
            <button
              key={session.id}
              type="button"
              onClick={() => void openSession(session.id)}
              className={`mb-1 w-full rounded-lg px-3 py-2 text-left text-sm ${
                session.id === thread?.sessionId ? "bg-accent/15 text-ink" : "text-muted hover:bg-line/40"
              }`}
            >
              <div className="truncate">{session.title || "未命名对话"}</div>
            </button>
          ))}
        </div>
        <button
          type="button"
          className="m-3 rounded-lg border border-line px-3 py-2 text-sm text-muted"
          onClick={() => setDark((v) => !v)}
        >
          {dark ? "浅色" : "深色"}
        </button>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">
        <AnimatePresence mode="wait">
          {pane === "chat" ? (
            <motion.section
              key="chat"
              className="flex min-h-0 flex-1 flex-col"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
            >
              <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto px-8 py-6">
                {(thread?.items || []).map((item, idx) => (
                  <Bubble key={`${item.ts || idx}-${idx}`} role={item.role} text={item.text} />
                ))}
                {status ? <div className="text-sm italic text-muted">{status}</div> : null}
                {error ? <div className="text-sm text-red-700 dark:text-red-300">{error}</div> : null}
              </div>
              <form
                className="flex gap-2 border-t border-line px-6 py-4"
                onSubmit={(ev) => {
                  ev.preventDefault();
                  send();
                }}
              >
                <input
                  value={draft}
                  onChange={(ev) => setDraft(ev.target.value)}
                  placeholder="问今天干什么，或直接跟凯尔希说"
                  className="flex-1 rounded-xl border border-line bg-panel px-4 py-3 outline-none"
                />
                <button
                  type="submit"
                  disabled={busy}
                  className="rounded-xl bg-accent px-5 text-white disabled:opacity-50"
                >
                  发送
                </button>
              </form>
            </motion.section>
          ) : (
            <motion.section
              key="board"
              className="flex-1 overflow-y-auto px-8 py-6"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
            >
              <h1 className="mb-4 text-xl font-semibold">今日看板</h1>
              <pre className="whitespace-pre-wrap rounded-2xl bg-panel p-5 text-sm leading-7">{boardText}</pre>
            </motion.section>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}

function NavButton(props: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={props.onClick}
      className={`rounded-lg px-3 py-1.5 text-sm ${
        props.active ? "bg-accent text-white" : "text-muted"
      }`}
    >
      {props.label}
    </button>
  );
}

function Bubble(props: { role: string; text: string }) {
  const mine = props.role === "user";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[70%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-6 ${
          mine ? "bg-accent text-white" : "bg-panel"
        }`}
      >
        {props.text || "…"}
      </div>
    </div>
  );
}
