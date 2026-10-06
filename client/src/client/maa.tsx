import { Button } from "reend-components";
import { sourceLabel, type Analysis, type LogItem } from "./maa-rules";

// MAA 页只展示接口和技能表里已有的句子。分析不调用模型。

export type MaaSnap = {
  ok?: boolean;
  error?: string;
  status?: string;
  message?: string;
  running?: boolean;
  current_task?: string;
  task_error?: string;
};

export type LogColumn = {
  path?: string;
  note?: string;
  items?: LogItem[];
};

export type LogPayload = {
  ok?: boolean;
  error?: string;
  highlights?: LogItem[];
  desk?: LogColumn;
  maa_gui?: LogColumn;
  maa_depot?: LogColumn;
};

export function maaMessage(snap: MaaSnap | null): string {
  if (!snap) return "";
  if (snap.ok === false) return snap.error || snap.message || "读取 MAA 失败。";
  return snap.message || "";
}

export function maaFailed(snap: MaaSnap | null): boolean {
  if (!snap) return false;
  if (snap.ok === false || snap.status === "error") return true;
  return typeof snap.task_error === "string" && snap.task_error.trim().length > 0;
}

export function MaaPane(props: {
  snap: MaaSnap | null;
  logs: LogPayload | null;
  logError: string;
  rulesError: string;
  analysis: Analysis | null;
  busy: boolean;
  loading: boolean;
  debug: boolean;
  onBack: () => void;
  onStart: () => void;
  onStop: () => void;
  onAnalyze: () => void;
}) {
  const running = props.snap?.running === true;
  const message = maaMessage(props.snap);
  const failed = maaFailed(props.snap);
  const task = props.snap?.current_task?.trim() || "";
  const taskError = props.snap?.task_error?.trim() || "";
  return (
    <div data-maa data-maa-running={running ? "1" : "0"}>
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">清日常</h1>
          <div className="mt-1 text-sm text-muted-foreground">开始、停止，以及今日出错原文</div>
        </div>
        <Button type="button" variant="secondary" size="sm" onClick={props.onBack}>
          返回看板
        </Button>
      </div>
      {props.debug ? <div className="mb-4 text-xs text-muted-foreground">调试样本，未连接后端</div> : null}
      {props.loading ? <p className="mb-4 text-sm text-muted-foreground">正在读取 MAA…</p> : null}
      {message ? (
        <p data-maa-message className={`text-sm leading-6 ${failed ? "text-destructive" : ""}`}>
          {message}
        </p>
      ) : null}
      {running && task ? (
        <p data-maa-task className="mt-2 text-sm text-muted-foreground">
          当前任务：{task}
        </p>
      ) : null}
      {taskError ? <p data-maa-task-error className="mt-2 text-sm text-destructive">任务出错：{taskError}</p> : null}
      <div className="mt-4 flex gap-2">
        <Button type="button" variant="primary" data-maa-start disabled={props.busy || running} onClick={props.onStart}>
          开始清日常
        </Button>
        <Button type="button" variant="secondary" data-maa-stop disabled={props.busy || !running} onClick={props.onStop}>
          停止
        </Button>
      </div>
      {props.logError ? <p data-maa-log-error className="mt-6 text-sm text-destructive">{props.logError}</p> : null}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <LogBlock title="重点" items={props.logs?.highlights || []} />
        <LogBlock title="桌宠" path={props.logs?.desk?.path} note={props.logs?.desk?.note} items={props.logs?.desk?.items || []} />
        <LogBlock title="MAA GUI" path={props.logs?.maa_gui?.path} note={props.logs?.maa_gui?.note} items={props.logs?.maa_gui?.items || []} />
        <LogBlock title="Depot" path={props.logs?.maa_depot?.path} note={props.logs?.maa_depot?.note} items={props.logs?.maa_depot?.items || []} />
      </div>
      <div className="mt-6">
        <Button type="button" variant="secondary" size="sm" data-maa-analyze disabled={props.busy} onClick={props.onAnalyze}>
          分析
        </Button>
        {props.rulesError ? <p data-maa-rules-error className="mt-3 text-sm text-destructive">{props.rulesError}</p> : null}
        <AnalysisBlock analysis={props.analysis} />
      </div>
    </div>
  );
}

function LogBlock(props: { title: string; path?: string; note?: string; items: LogItem[] }) {
  return (
    <section data-maa-column={props.title} className="border border-border bg-card/80 p-4">
      <h2 className="text-xs text-muted-foreground">{props.title}</h2>
      {props.path ? <p data-maa-path className="mt-2 break-all text-xs text-muted-foreground">{props.path}</p> : null}
      {props.note ? <p className="mt-2 text-sm text-muted-foreground">{props.note}</p> : null}
      {props.items.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">今日没有这段。</p> : null}
      <ul className="mt-2 space-y-3">
        {props.items.map((item, index) => (
          <li key={`${item.time || ""}-${item.title || ""}-${index}`} data-maa-item>
            <div className="text-xs text-muted-foreground">{[item.time, item.title].filter(Boolean).join(" ")}</div>
            <pre className="mt-1 whitespace-pre-wrap text-sm leading-6">{item.text}</pre>
          </li>
        ))}
      </ul>
    </section>
  );
}

function AnalysisBlock(props: { analysis: Analysis | null }) {
  const analysis = props.analysis;
  if (!analysis) return null;
  if (analysis.kind === "bad") {
    return <p data-maa-analysis data-maa-kind="bad" className="mt-3 text-sm text-destructive">{analysis.message}</p>;
  }
  if (analysis.kind === "empty") {
    return <p data-maa-analysis data-maa-kind="empty" className="mt-3 text-sm">没有问题记录</p>;
  }
  if (analysis.kind === "none") {
    return <p data-maa-analysis data-maa-kind="none" className="mt-3 text-sm">文档没有这一条</p>;
  }
  return (
    <ul data-maa-analysis data-maa-kind="hits" className="mt-3 space-y-2">
      {analysis.hits.map((hit) => (
        <li key={hit.id} data-maa-hit data-source={hit.source} className="border border-border px-3 py-2 text-sm leading-6">
          <span className="mr-2 text-xs text-muted-foreground">{sourceLabel(hit.source)}</span>
          {hit.text}
        </li>
      ))}
    </ul>
  );
}

export function columnItems(logs: LogPayload | null): LogItem[] {
  if (!logs || logs.ok === false) return [];
  return [
    ...(logs.highlights || []),
    ...(logs.desk?.items || []),
    ...(logs.maa_gui?.items || []),
    ...(logs.maa_depot?.items || []),
  ];
}
