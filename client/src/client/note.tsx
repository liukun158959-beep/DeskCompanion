import { useRef, useState, type PointerEvent as ReactPointerEvent, type Ref } from "react";
import { motion } from "framer-motion";
import { Markdown } from "./Markdown";

export type NoteCite = {
  n: number;
  doc: string;
  title: string;
  text: string;
  doc_id: string;
  context?: string;
};

export type NoteTurn = {
  role: string;
  text: string;
  cites?: NoteCite[];
};

export type NoteFile = {
  name: string;
  path: string;
  saved: string;
};

export type NoteItem = {
  id: string;
  question: string;
  answer: string;
  cites: NoteCite[];
  saved: string;
  files: NoteFile[];
};

export type NoteDoc = {
  id: string;
  title: string;
  chars: number;
  chunks: number;
};

export type NoteSession = {
  id: string;
  title: string;
  updated: string;
  turns: NoteTurn[];
  notes: NoteItem[];
};

export type NotebookPage = {
  ok?: boolean;
  error?: string;
  docs?: NoteDoc[];
  sessions?: NoteSession[];
  session_id?: string;
  url?: string;
  path?: string;
  message?: string;
};

const columnEase = [0.22, 1, 0.36, 1] as const;

export function NoteMode(props: {
  sessionId: string;
  book: { docs: NoteDoc[]; turns: NoteTurn[]; notes: NoteItem[] } | null;
  error: string;
  busy: boolean;
  status: string;
  checked: string[];
  onCheck: (id: string, on: boolean) => void;
  onSave: (index: number) => void;
  onDelete: (id: string) => void;
  onMarkdown: (id: string) => void;
  onFeishu: (id: string) => void;
  onOpenFile: (id: string, name: string) => void;
  onRevealFile: (id: string, name: string) => void;
  onDeleteFile: (id: string, name: string) => void;
  onSummarize: (noteIds: string[]) => void;
  saveStatus: string;
  saveBad: boolean;
  docUrl: string;
  threadRef?: Ref<HTMLDivElement>;
}) {
  const book = props.book;
  const docs = book?.docs || [];
  const turns = book?.turns || [];
  const notes = book?.notes || [];
  const boardRef = useRef<HTMLDivElement>(null);
  const [sourceW, setSourceW] = useState(224);
  const [notesW, setNotesW] = useState(256);
  const [openAnswers, setOpenAnswers] = useState<string[]>([]);
  const [pickedAnswers, setPickedAnswers] = useState<string[]>([]);
  const picked = notes.filter((note) => pickedAnswers.includes(note.id));

  function dragColumn(side: "source" | "notes", ev: ReactPointerEvent<HTMLButtonElement>) {
    ev.preventDefault();
    const board = boardRef.current;
    if (!board) return;
    try {
      ev.currentTarget.setPointerCapture(ev.pointerId);
    } catch {
      // 抓不到指针时仍靠 window 上的移动事件收尾。
    }
    const origin = ev.clientX;
    const startSource = sourceW;
    const startNotes = notesW;
    const move = (e: PointerEvent) => {
      const total = board.getBoundingClientRect().width;
      const dx = e.clientX - origin;
      const handles = 12;
      const centerMin = 220;
      if (side === "source") {
        const max = Math.max(160, total - startNotes - centerMin - handles);
        setSourceW(Math.round(Math.min(Math.max(160, startSource + dx), max)));
        return;
      }
      const max = Math.max(180, total - startSource - centerMin - handles);
      setNotesW(Math.round(Math.min(Math.max(180, startNotes - dx), max)));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  return (
    <div ref={boardRef} className="flex min-h-0 flex-1" data-note-board="" data-note-session={props.sessionId}>
      <motion.aside
        className="shrink-0 overflow-y-auto border-r border-border px-3 py-4"
        style={{ width: sourceW }}
        data-note-sources=""
        data-note-source-width={sourceW}
        initial={{ opacity: 0, x: -18 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.38, ease: columnEase }}
      >
        <h2 className="text-sm font-semibold">来源</h2>
        {docs.length === 0 ? <p className="mt-3 text-xs text-muted-foreground">库里还没有文档。恢复：在知识库页加入飞书文档。</p> : null}
        <div className="mt-3 space-y-2">
          {docs.map((doc) => {
            const on = props.checked.includes(doc.id);
            return (
              <label key={doc.id} data-note-source={doc.id} data-checked={on ? "1" : "0"} className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={on}
                  disabled={props.busy}
                  onChange={(ev) => props.onCheck(doc.id, ev.target.checked)}
                />
                <span>
                  {doc.title}
                  <span className="mt-1 block text-xs text-muted-foreground">{doc.chars} 字 · {doc.chunks} 块</span>
                </span>
              </label>
            );
          })}
        </div>
      </motion.aside>
      <button
        type="button"
        aria-orientation="vertical"
        data-note-resize="sources"
        aria-label="拖来源栏"
        className="w-1.5 shrink-0 cursor-col-resize border-0 bg-border p-0 hover:bg-primary/50"
        onPointerDown={(ev) => dragColumn("source", ev)}
      />
      <motion.div
        className="flex min-w-0 flex-1 flex-col"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.38, delay: 0.05, ease: columnEase }}
      >
        <div ref={props.threadRef} className="flex-1 space-y-3 overflow-y-auto px-6 py-4" data-note-thread="">
          {turns.length === 0 ? <p className="text-sm text-muted-foreground">勾选来源后，在下面提问。回答只用来源里的原文。</p> : null}
          {turns.map((turn, index) => (
            <article key={`${turn.role}-${index}`} data-note-turn="" data-role={turn.role} className="border border-border px-3 py-2 text-sm">
              <p className="text-xs text-muted-foreground">{turn.role === "user" ? "问题" : "回答"}</p>
              {turn.role === "pet" && turn.text ? <CitedText text={turn.text} cites={turn.cites || []} /> : null}
              {turn.role === "pet" && !turn.text && props.status ? (
                <p data-note-status="" className="mt-1 text-sm italic text-muted-foreground">{props.status}</p>
              ) : null}
              {turn.role === "user" ? <p className="mt-1 whitespace-pre-wrap">{turn.text}</p> : null}
              {turn.role === "pet" && turn.text && turn.cites && turn.cites.length ? (
                <button
                  type="button"
                  data-note-save=""
                  disabled={props.busy}
                  className="mt-2 desk-btn desk-btn-solid"
                  onClick={() => props.onSave(index)}
                >
                  存成笔记
                </button>
              ) : null}
            </article>
          ))}
          {props.error ? <p data-note-error="" className="text-sm text-destructive">{props.error}</p> : null}
        </div>
      </motion.div>
      <button
        type="button"
        aria-orientation="vertical"
        data-note-resize="notes"
        aria-label="拖笔记栏"
        className="w-1.5 shrink-0 cursor-col-resize border-0 bg-border p-0 hover:bg-primary/50"
        onPointerDown={(ev) => dragColumn("notes", ev)}
      />
      <motion.aside
        className="shrink-0 overflow-y-auto border-l border-border px-3 py-4"
        style={{ width: notesW }}
        data-note-notes=""
        data-note-notes-width={notesW}
        initial={{ opacity: 0, x: 18 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.38, delay: 0.08, ease: columnEase }}
      >
        <h2 className="text-sm font-semibold">笔记</h2>
        <button
          type="button"
          data-note-summarize=""
          data-note-summarize-count={picked.length}
          disabled={props.busy || picked.length === 0}
          className="mt-3 desk-btn desk-btn-solid"
          onClick={() => props.onSummarize(picked.map((note) => note.id))}
        >
          总结成一份文档
        </button>
        {notes.length === 0 ? <p className="mt-3 text-xs text-muted-foreground">还没有笔记。回答下面可以存成笔记。</p> : null}
        <div className="mt-3 space-y-2">
          {notes.map((note) => {
            const open = openAnswers.includes(note.id);
            return (
            <article key={note.id} data-note-item={note.id} data-note-answer={note.id} data-open={open ? "1" : "0"} className="border border-border px-2 py-2 text-sm">
              <p className="text-xs text-muted-foreground">{note.saved}</p>
              <div className="mt-1 flex items-start gap-2">
                <input
                  type="checkbox"
                  aria-label={note.question}
                  data-note-answer-pick={note.id}
                  checked={pickedAnswers.includes(note.id)}
                  disabled={props.busy}
                  onChange={(ev) => {
                    const on = ev.target.checked;
                    setPickedAnswers((cur) => on ? [...cur, note.id] : cur.filter((item) => item !== note.id));
                  }}
                />
                <button
                  type="button"
                  data-note-answer-toggle={note.id}
                  aria-expanded={open}
                  className="min-w-0 flex-1 text-left"
                  onClick={() => setOpenAnswers((cur) => open ? cur.filter((item) => item !== note.id) : [...cur, note.id])}
                >
                  <span data-note-theme="" className="desk-answer-theme">{note.question}</span>
                </button>
              </div>
              {open ? <CitedText text={note.answer} cites={note.cites} /> : null}
              {(note.files || []).map((file) => (
                <div key={file.name} data-note-file={file.name} data-note-file-path={file.path} className="mt-2 border border-border px-2 py-2">
                  <p className="text-xs font-semibold">{file.name}</p>
                  <p className="mt-1 break-all text-xs text-muted-foreground">{file.path}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button type="button" data-note-file-open={file.name} disabled={props.busy} className="desk-btn" onClick={() => props.onOpenFile(note.id, file.name)}>打开</button>
                    <button type="button" data-note-file-reveal={file.name} disabled={props.busy} className="desk-btn" onClick={() => props.onRevealFile(note.id, file.name)}>文件夹</button>
                    <button type="button" data-note-file-delete={file.name} disabled={props.busy} className="desk-btn desk-btn-danger" onClick={() => props.onDeleteFile(note.id, file.name)}>删除文件</button>
                  </div>
                </div>
              ))}
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  data-note-markdown={note.id}
                  disabled={props.busy}
                  className="desk-btn"
                  onClick={() => props.onMarkdown(note.id)}
                >
                  Markdown
                </button>
                <button
                  type="button"
                  data-note-feishu={note.id}
                  disabled={props.busy}
                  className="desk-btn"
                  onClick={() => props.onFeishu(note.id)}
                >
                  飞书文档
                </button>
                <button
                  type="button"
                  data-note-delete={note.id}
                  disabled={props.busy}
                  className="desk-btn desk-btn-danger"
                  onClick={() => props.onDelete(note.id)}
                >
                  删除
                </button>
              </div>
            </article>
            );
          })}
        </div>
        {props.saveStatus ? (
          <p data-note-save-status="" className={`mt-3 text-xs ${props.saveBad ? "text-destructive" : "text-foreground"}`}>{props.saveStatus}</p>
        ) : null}
        {props.docUrl ? <p data-note-doc-url={props.docUrl} className="mt-2 break-all text-xs text-primary">{props.docUrl}</p> : null}
      </motion.aside>
    </div>
  );
}

function CitedText(props: { text: string; cites: NoteCite[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const quote = props.cites.find((item) => item.n === open) || null;
  return (
    <div className="mt-1" data-note-markdown-body="">
      <Markdown text={props.text} cites={props.cites.map((item) => item.n)} onCite={(n) => setOpen((cur) => (cur === n ? null : n))} />
      {quote ? (
        <div data-note-quote="" data-n={quote.n} className="mt-2 border border-border px-2 py-1 text-xs">
          <p>{quote.doc} · {quote.title}</p>
          <p className="mt-1 whitespace-pre-wrap">{quote.context || quote.text}</p>
        </div>
      ) : null}
    </div>
  );
}
