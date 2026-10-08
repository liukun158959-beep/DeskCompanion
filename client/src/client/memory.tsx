import { useState, type ReactNode } from "react";
import { PlainLinks } from "./Markdown";

export type MemoryFact = {
  id: string;
  text: string;
  writer: string;
  quote: string;
  updated: string;
};

export type MemoryTurn = {
  role: string;
  text: string;
};

export type ContextView = {
  budget: number;
  tool_reserve: number;
  before: number;
  estimate: number;
  saved: number;
  summary: string;
  covered: MemoryTurn[];
  over: boolean;
};

export type MemoryPayload = {
  ok?: boolean;
  error?: string;
  total?: number;
  fact_limit?: number;
  facts?: MemoryFact[];
  items?: MemoryTurn[];
  context?: ContextView;
};

function turnKey(role: string, text: string): string {
  return `${role}\n${text}`;
}

/** 与 context_pack.estimate_tokens 同一把尺子：汉字和标点各 1，连续英文或数字每 4 个字符 1。 */
export function estimateTokens(text: string): number {
  let tokens = 0;
  let asciiRun = 0;
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0;
    if (code <= 0x7f && !/\s/.test(ch)) {
      asciiRun += 1;
      continue;
    }
    if (asciiRun) {
      tokens += Math.floor((asciiRun + 3) / 4);
      asciiRun = 0;
    }
    tokens += 1;
  }
  if (asciiRun) tokens += Math.floor((asciiRun + 3) / 4);
  return tokens;
}

export function coveredStats(covered: MemoryTurn[]): { chars: number; tokens: number } {
  let chars = 0;
  let tokens = 0;
  for (const item of covered) {
    const text = item.text.trim();
    chars += [...text].length;
    tokens += 4 + estimateTokens(text);
  }
  return { chars, tokens };
}

export function splitIndex(items: { role: string; text: string }[], covered: MemoryTurn[]): number {
  if (!covered.length) return -1;
  const keys = new Set(covered.map((item) => turnKey(item.role, item.text.trim())));
  const idx = items.findIndex((item) => !keys.has(turnKey(item.role, (item.text || "").trim())));
  return idx === -1 ? items.length : idx;
}

/** 去重后还没收进摘要的句子。顺序与 session_for_model 再去掉 covered 相同。 */
export function modelVerbatim(items: { role: string; text: string }[], covered: MemoryTurn[]): MemoryTurn[] {
  const coveredKeys = new Set(covered.map((item) => turnKey(item.role, item.text.trim())));
  const kept: MemoryTurn[] = [];
  const seen = new Set<string>();
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const role = items[i].role;
    const text = (items[i].text || "").trim();
    if (role !== "user" && role !== "pet") continue;
    if (!text) continue;
    const key = turnKey(role, text);
    if (seen.has(key)) continue;
    seen.add(key);
    if (coveredKeys.has(key)) continue;
    kept.push({ role, text });
  }
  kept.reverse();
  return kept;
}

function FactText(props: {
  fact: MemoryFact;
  busy: boolean;
  onUpdate: (id: string, text: string) => Promise<boolean>;
}) {
  const [value, setValue] = useState(props.fact.text);
  const [focused, setFocused] = useState(false);
  const dirty = value !== props.fact.text;
  const bright = focused || dirty;
  return (
    <form
      className="min-w-0 flex-1"
      onSubmit={(ev) => {
        ev.preventDefault();
        void props.onUpdate(props.fact.id, value);
      }}
    >
      <div className="mb-2 text-xs text-muted-foreground">
        {writerLabel(props.fact.writer)} · {props.fact.updated.replace("T", " ")}
      </div>
      <input
        data-memory-edit
        data-memory-tone={bright ? "edit" : "saved"}
        value={value}
        onChange={(ev) => setValue(ev.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        className={`w-full border border-border bg-background px-2 py-1 text-sm focus:text-foreground ${
          bright ? "text-foreground" : "text-muted-foreground"
        }`}
      />
      {props.fact.quote ? (
        <p data-memory-quote className="mt-2 text-xs text-muted-foreground">
          依据：{props.fact.quote}
        </p>
      ) : null}
      <div className="mt-2">
        <button type="submit" data-memory-save disabled={props.busy} className="desk-btn desk-btn-solid">
          保存
        </button>
      </div>
    </form>
  );
}

function writerLabel(writer: string): string {
  if (writer === "user") return "你";
  if (writer === "model") return "模型";
  return writer;
}

export function MemoryPane(props: {
  data: MemoryPayload | null;
  loading: boolean;
  formError: string;
  busy: boolean;
  onAdd: (text: string) => Promise<boolean>;
  onUpdate: (id: string, text: string) => Promise<boolean>;
  onDelete: (id: string) => Promise<boolean>;
  onDrop: (role: string, text: string) => Promise<boolean>;
  onCompress: () => Promise<boolean>;
}) {
  const data = props.data;
  const failed = !data || data.ok === false;
  const facts = failed ? [] : data.facts || [];
  const items = failed ? [] : data.items || [];
  const context = failed ? null : data.context || null;
  const [draft, setDraft] = useState("");
  const [pickedFacts, setPickedFacts] = useState<string[]>([]);
  const [pickedTurns, setPickedTurns] = useState<string[]>([]);
  const covered = context?.covered || [];
  const factPicked = pickedFacts.filter((id) => facts.some((fact) => fact.id === id));
  const turnPicked = [...covered, ...items].filter((item) => pickedTurns.includes(turnKey(item.role, item.text)));
  const pickedCount = factPicked.length + turnPicked.length;

  async function removePicked() {
    for (const id of factPicked) {
      const ok = await props.onDelete(id);
      if (!ok) return;
      setPickedFacts((prev) => prev.filter((item) => item !== id));
    }
    for (const item of turnPicked) {
      const ok = await props.onDrop(item.role, item.text);
      if (!ok) return;
      setPickedTurns((prev) => prev.filter((key) => key !== turnKey(item.role, item.text)));
    }
  }

  return (
    <div
      data-memory
      data-memory-ok={data ? (failed ? "0" : "1") : ""}
      data-memory-limit={data?.fact_limit ?? ""}
    >
      <div className="mb-6">
        <h1 className="text-xl font-semibold">记忆</h1>
        <div className="mt-1 text-sm text-muted-foreground">
          上面的事实换一条对话还在。下面只喂当前这一条对话。勾选后再删。
        </div>
      </div>
      {facts.length > 0 || items.length > 0 || covered.length > 0 ? (
        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            data-memory-delete-selected
            data-count={pickedCount}
            disabled={props.busy || pickedCount === 0}
            onClick={() => void removePicked()}
            className={
              pickedCount === 0
                ? "desk-btn desk-btn-lg desk-btn-danger"
                : "desk-btn desk-btn-lg desk-btn-danger desk-btn-danger-solid"
            }
          >
            删除所选
          </button>
          <span data-memory-pick-count className="text-sm text-muted-foreground">
            {pickedCount === 0 ? "先勾选要删的事实或对话" : `已选 ${pickedCount} 条`}
          </span>
        </div>
      ) : null}
      {props.loading ? <p className="text-sm text-muted-foreground">正在读取…</p> : null}
      {failed && data?.error ? (
        <p data-memory-error className="text-sm text-destructive">
          {data.error}
        </p>
      ) : null}
      <section className="mt-6">
        <h2 className="text-sm font-semibold">事实</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          要跨会话记住，写在这里，或在对话里把原话说出来让模型记。写满 {data?.fact_limit || 30} 条要先删一条。
        </p>
        <form
          className="mt-3 flex gap-2"
          onSubmit={(ev) => {
            ev.preventDefault();
            void props.onAdd(draft.trim()).then((ok) => {
              if (ok) setDraft("");
            });
          }}
        >
          <input
            data-memory-new
            value={draft}
            onChange={(ev) => setDraft(ev.target.value)}
            placeholder="写一条要跨对话记住的事实"
            className="flex-1 border border-border bg-card px-3 py-2 text-sm"
          />
          <button type="submit" data-memory-add disabled={props.busy} className="desk-btn desk-btn-lg desk-btn-solid">
            记下
          </button>
        </form>
        {props.formError ? (
          <p data-memory-form-error className="mt-2 text-sm text-destructive">
            {props.formError}
          </p>
        ) : null}
        <div className="mt-4 space-y-3">
          {facts.map((fact) => (
            <div
              key={`${fact.id}:${fact.updated}:${fact.text}`}
              data-memory-fact
              data-id={fact.id}
              data-writer={fact.writer}
              data-text={fact.text}
              data-quote={fact.quote}
              data-updated={fact.updated}
              data-picked={factPicked.includes(fact.id) ? "1" : "0"}
              className="flex items-start gap-3 border border-border px-3 py-3"
            >
              <input
                type="checkbox"
                data-memory-pick="fact"
                data-key={fact.id}
                checked={factPicked.includes(fact.id)}
                disabled={props.busy}
                onChange={(ev) => {
                  const on = ev.target.checked;
                  setPickedFacts((prev) => (on ? [...prev, fact.id] : prev.filter((id) => id !== fact.id)));
                }}
                className="mt-1 h-5 w-5 shrink-0 accent-red-500"
              />
              <FactText fact={fact} busy={props.busy} onUpdate={props.onUpdate} />
            </div>
          ))}
        </div>
      </section>
      <section className="mt-8">
        <h2 className="text-sm font-semibold">这一线程会喂给模型的对话</h2>
        <p data-memory-window-note className="mt-2 text-sm text-muted-foreground">
          当前对话去重后全量注入。{context ? reductionText(context) : "还没有上下文估算"}。
          {context?.summary
            ? "发给模型的是摘要，加上还没压的原文。已经收进摘要的原句只留在对话里。"
            : `全部按原文发给模型。全部对话 ${data?.total ?? 0} 条。`}
          删掉只影响这一线程。思考和 token 不在这里。
        </p>
        {failed ? null : (
          <div className="mt-3">
            <ContextCard
              context={context}
              verbatim={items}
              busy={props.busy}
              onCompress={props.onCompress}
              picked={(role, text) => pickedTurns.includes(turnKey(role, text))}
              onToggle={(role, text, on) => {
                const key = turnKey(role, text);
                setPickedTurns((prev) => (on ? [...prev, key] : prev.filter((item) => item !== key)));
              }}
            />
          </div>
        )}
        {context?.summary ? null : (
        <div className="mt-3 space-y-2">
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground">还没有会按原文喂给模型的对话。</p>
          ) : null}
          {items.map((item, idx) => (
                <div
                  key={`${item.role}-${idx}`}
                  data-memory-window
                  data-role={item.role}
                  data-picked={turnPicked.some((row) => row.role === item.role && row.text === item.text) ? "1" : "0"}
                  className="flex items-start gap-3 text-sm"
                >
                  <input
                    type="checkbox"
                    data-memory-pick="turn"
                    data-key={item.role}
                    checked={turnPicked.some((row) => row.role === item.role && row.text === item.text)}
                    disabled={props.busy}
                    onChange={(ev) => {
                      const key = turnKey(item.role, item.text);
                      const on = ev.target.checked;
                      setPickedTurns((prev) => (on ? [...prev, key] : prev.filter((itemKey) => itemKey !== key)));
                    }}
                    className="mt-0.5 h-5 w-5 shrink-0 accent-red-500"
                  />
                  <div data-memory-line>
                    <span className="text-muted-foreground">{item.role === "user" ? "你" : "凯尔希"}</span>
                    {" "}
                    {item.role === "user" ? <PlainLinks text={item.text} /> : item.text}
              </div>
            </div>
          ))}
        </div>
        )}
      </section>
    </div>
  );
}

export function ContextCard(props: {
  context: ContextView | null;
  verbatim?: MemoryTurn[];
  busy: boolean;
  onCompress: () => Promise<boolean>;
  picked?: (role: string, text: string) => boolean;
  onToggle?: (role: string, text: string, on: boolean) => void;
  variant?: "panel" | "bar";
  leading?: ReactNode;
}) {
  const [opened, setOpened] = useState(false);
  const context = props.context;
  const bar = props.variant === "bar";
  if (!context) {
    return (
      <div className={bar ? "mb-2 flex items-center gap-3" : undefined}>
        {props.leading}
        <p data-context-missing className="text-sm text-destructive">
          还没有上下文估算。恢复：停掉当前客户端，在 desk-companion\client 里重新运行 pnpm tauri dev。
        </p>
      </div>
    );
  }
  const covered = context.covered || [];
  const verbatim = props.verbatim || [];
  const hint = `${reductionText(context)}${context.over ? " · 下次发送会先压缩" : ""}`;
  if (bar) {
    return (
      <div
        data-context=""
        data-context-place="bar"
        data-context-budget={context.budget}
        data-context-before={context.before}
        data-context-estimate={context.estimate}
        data-context-saved={context.saved}
        data-context-over={context.over ? "1" : "0"}
        className="mb-2 text-sm"
      >
        <div className="flex items-center gap-3">
          {props.leading}
          <button
            type="button"
            data-context-toggle=""
            aria-expanded={opened}
            className="min-w-0 flex-1 truncate text-left text-xs text-muted-foreground"
            onClick={() => setOpened((value) => !value)}
          >
            {hint}
          </button>
          <button
            type="button"
            data-context-compress=""
            disabled={props.busy}
            className="shrink-0 desk-btn"
            onClick={() => void props.onCompress()}
          >
            压缩更早的对话
          </button>
        </div>
        <ContextMeter context={context} />
        {opened ? (
          <ContextBody
            context={context}
            covered={covered}
            verbatim={verbatim}
            busy={props.busy}
            picked={props.picked}
            onToggle={props.onToggle}
          />
        ) : null}
      </div>
    );
  }
  return (
    <div
      data-context=""
      data-context-budget={context.budget}
      data-context-before={context.before}
      data-context-estimate={context.estimate}
      data-context-saved={context.saved}
      data-context-over={context.over ? "1" : "0"}
      className="border border-border px-3 py-3 text-sm"
    >
      <div className="flex items-center justify-between gap-3">
        <p>
          {reductionText(context)}
          {context.over ? "，下一次发送会先压缩" : ""}
        </p>
        <button
          type="button"
          data-context-compress=""
          disabled={props.busy}
          className="desk-btn"
          onClick={() => void props.onCompress()}
        >
          压缩更早的对话
        </button>
      </div>
      <ContextBody
        context={context}
        covered={covered}
        verbatim={verbatim}
        busy={props.busy}
        picked={props.picked}
        onToggle={props.onToggle}
      />
    </div>
  );
}

function triggerCap(context: ContextView): number {
  return context.budget - context.tool_reserve;
}

function reductionText(context: ContextView): string {
  const cap = triggerCap(context);
  if (!context.summary) {
    return `估算 ${context.estimate} / ${cap}`;
  }
  if (typeof context.before !== "number" || typeof context.saved !== "number") {
    return "压缩前后的差额还没有返回。恢复：停掉当前客户端，在 desk-companion\\client 里重新运行 pnpm tauri dev。";
  }
  const delta = context.saved;
  const change = delta >= 0 ? `少 ${delta}` : `多 ${-delta}`;
  return `原文 ${context.before} → ${context.estimate}，${change}`;
}

function ContextMeter(props: { context: ContextView }) {
  const cap = triggerCap(props.context);
  const percent = cap <= 0 ? 100 : Math.round((props.context.estimate / cap) * 100);
  const fill = Math.min(100, percent);
  const label = `${percent}% · ${props.context.estimate} / ${cap}`;
  return (
    <div className="mt-2 flex items-center gap-3">
      <div
        data-context-meter=""
        data-context-progress={percent}
        data-context-cap={cap}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={cap}
        aria-valuenow={props.context.estimate}
        aria-label={label}
        className="h-1 min-w-0 flex-1"
        style={{ background: "hsl(var(--border))" }}
      >
        <div className="h-full" style={{ width: `${fill}%`, background: "hsl(var(--primary))" }} />
      </div>
      <span data-context-meter-label="" className="shrink-0 text-xs text-foreground">
        {label}
      </span>
    </div>
  );
}

export function ContextSplit(props: { covered: MemoryTurn[] }) {
  if (!props.covered.length) return null;
  const stats = coveredStats(props.covered);
  return (
    <div data-context-split="" data-context-chars={stats.chars} data-context-tokens={stats.tokens} className="py-1">
      <div className="h-px w-full" style={{ background: "hsl(var(--border))" }} />
      <p className="mt-1 text-center text-xs text-muted-foreground">
        {`以上已压缩 · ${stats.chars} 字 · 估算 ${stats.tokens} token`}
      </p>
    </div>
  );
}

function ContextBody(props: {
  context: ContextView;
  covered: MemoryTurn[];
  verbatim: MemoryTurn[];
  busy: boolean;
  picked?: (role: string, text: string) => boolean;
  onToggle?: (role: string, text: string, on: boolean) => void;
}) {
  if (!props.context.summary) {
    return (
      <p data-context-summary="" className="mt-2 text-muted-foreground">
        全部按原文发给模型。
      </p>
    );
  }
  return (
    <div className="mt-3 max-h-64 space-y-3 overflow-y-auto">
      <section data-context-sent="" className="border-l-2 py-1 pl-3" style={{ borderColor: "hsl(var(--primary))" }}>
        <h3 className="text-sm font-semibold">发给模型</h3>
        <p className="mt-2 text-xs text-muted-foreground">摘要</p>
        <p data-context-summary className="mt-1 whitespace-pre-wrap">
          {props.context.summary}
        </p>
        <div data-context-verbatim-block="" className="mt-3 border px-3 py-2" style={{ borderColor: "hsl(var(--primary) / 0.55)" }}>
          <h4 className="text-sm font-semibold">仍按原文</h4>
          {props.verbatim.length === 0 ? (
            <p className="mt-1 text-muted-foreground">没有仍按原文发送的句子。</p>
          ) : (
            <div className="mt-2 space-y-2">
              {props.verbatim.map((item, idx) => (
                <TurnLine
                  key={`${item.role}-${idx}`}
                  item={item}
                  mark="verbatim"
                  busy={props.busy}
                  picked={props.picked}
                  onToggle={props.onToggle}
                />
              ))}
            </div>
          )}
        </div>
      </section>
      <section data-context-local="" className="px-3 py-2" style={{ background: "hsl(var(--muted-foreground) / 0.12)" }}>
        <h3 className="text-sm font-semibold">只留在对话里</h3>
        {props.covered.length === 0 ? (
          <p className="mt-1 text-muted-foreground">没有只留在对话里的原句。</p>
        ) : (
          <div className="mt-2 space-y-2">
            {props.covered.map((item, idx) => (
              <TurnLine
                key={`${item.role}-${idx}`}
                item={item}
                mark="covered"
                busy={props.busy}
                picked={props.picked}
                onToggle={props.onToggle}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function TurnLine(props: {
  item: MemoryTurn;
  mark: "covered" | "verbatim";
  busy: boolean;
  picked?: (role: string, text: string) => boolean;
  onToggle?: (role: string, text: string, on: boolean) => void;
}) {
  return (
    <div
      data-context-covered={props.mark === "covered" ? "" : undefined}
      data-context-verbatim={props.mark === "verbatim" ? "" : undefined}
      data-memory-window={props.mark === "verbatim" && props.onToggle ? "" : undefined}
      data-role={props.item.role}
      className="flex items-start gap-3"
    >
      {props.onToggle ? (
        <input
          type="checkbox"
          data-memory-pick="turn"
          data-key={props.item.role}
          checked={props.picked ? props.picked(props.item.role, props.item.text) : false}
          className="mt-0.5 h-5 w-5 shrink-0 accent-red-500"
          disabled={props.busy}
          onChange={(ev) => props.onToggle?.(props.item.role, props.item.text, ev.target.checked)}
        />
      ) : null}
      <div data-memory-line>
        <span className="text-muted-foreground">{props.item.role === "user" ? "你" : "凯尔希"}</span>{" "}
        {props.item.role === "user" ? <PlainLinks text={props.item.text} /> : props.item.text}
      </div>
    </div>
  );
}
