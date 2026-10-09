import { useEffect, useRef, useState } from "react";
import { rpc, type BackendInfo } from "./api";
import { Markdown, MdLink } from "./Markdown";

type VideoEvent = { seq: number; kind: string; ts: number; data: string | { tool?: string; status?: string } };
type VideoTask = { id: string; channel: string; text: string; state: string; answer: string; error: string;
  created: number; elapsed: number; events?: VideoEvent[]; source: { video_url?: string } };
const STATES: Record<string, string> = { queued: "排队中", running: "读取与整理中", cancelling: "正在停止", succeeded: "已完成",
  failed: "失败", cancelled: "已停止", timed_out: "超时", interrupted: "上次运行中断" };
const active = (task: VideoTask) => ["queued", "running", "cancelling"].includes(task.state);

export function VideoPane({ info, debug = false }: { info: BackendInfo | null; debug?: boolean }) {
  const [url, setUrl] = useState("");
  const [question, setQuestion] = useState("");
  const [tasks, setTasks] = useState<VideoTask[]>([]);
  const [selected, select] = useState("");
  const [detail, setDetail] = useState<VideoTask | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [epoch, refresh] = useState(0);
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!info || debug) return;
    let live = true;
    let pending = false;
    const poll = async () => {
      if (pending) return;
      pending = true;
      try {
        const value = await rpc<{ items: VideoTask[] }>(info, "list_video_tasks");
        if (!live) return;
        setTasks(value.items);
        const id = selected || value.items[0]?.id;
        if (!id) { setDetail(null); return; }
        const result = await rpc<{ task: VideoTask }>(info, "get_agent_task", { task_id: id, focus: false });
        if (live) setDetail(result.task);
      } catch (err) { if (live) setError(String(err)); }
      finally { pending = false; }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 2000);
    return () => { live = false; window.clearInterval(timer); };
  }, [info, debug, selected, epoch]);

  async function run(method: string, args: Record<string, unknown>) {
    if (!info || debug || busy) return;
    setBusy(true); setError("");
    try {
      const result = await rpc<{ ok?: boolean; error?: string; task_id?: string; task?: VideoTask }>(info, method, args);
      if (result.ok === false) throw new Error(result.error || "视频任务未完成。");
      if (!mounted.current) return;
      if (result.task_id) { select(result.task_id); setDetail(null); setQuestion(""); }
      if (result.task) setDetail(result.task);
      refresh(value => value + 1);
    } catch (err) { if (mounted.current) setError(String(err)); }
    finally { if (mounted.current) setBusy(false); }
  }

  return <div className="mt-6 space-y-6" aria-label="视频读取工作区">
    <section className="rounded-2xl border border-border bg-card/70 p-5">
      <label htmlFor="video-url" className="block text-sm font-medium">视频链接</label>
      <div className="mt-2 flex flex-wrap gap-3">
        <input id="video-url" type="url" className="min-w-0 flex-1 rounded-lg border border-border bg-background p-3 text-sm"
          value={url} onChange={event => setUrl(event.target.value)} placeholder="粘贴 Bilibili / YouTube 单个视频链接" disabled={busy} />
        <button className="rounded-lg bg-primary px-5 py-3 text-sm text-primary-foreground disabled:opacity-40"
          disabled={!info || debug || busy || !url.trim()} onClick={() => void run("start_video_task", { url: url.trim() })}>
          {busy ? "正在提交…" : "读取并总结"}</button>
      </div>
      <p className="mt-3 text-sm text-muted-foreground">读取标题、简介、章节和实际字幕，生成带时间点的中文总结。没有取得字幕时会说明原因与覆盖范围。</p>
      <p className="mt-1 text-xs text-muted-foreground">每个新链接使用独立会话。切换页面后任务继续执行，可在此查看结果、追问并保存到飞书。</p>
    </section>
    <div className="grid gap-5 xl:grid-cols-[260px_minmax(0,1fr)]">
      <section className="rounded-2xl border border-border bg-card/70 p-4" aria-label="视频任务历史">
        <h2 className="font-medium">读取记录</h2>
        <p className="mt-1 text-xs text-muted-foreground">包含桌面对话和飞书聊天中的视频任务。</p>
        <div className="mt-4 max-h-[650px] space-y-2 overflow-auto">
          {!tasks.length && <p className="py-4 text-sm text-muted-foreground">粘贴一个视频链接开始读取。</p>}
          {tasks.map(task => <button key={task.id} disabled={busy}
            className={`block w-full rounded-lg border p-3 text-left ${detail?.id === task.id ? "border-primary bg-primary/10" : "border-border hover:bg-secondary"}`}
            onClick={() => { select(task.id); setDetail(null); setQuestion(""); setError(""); }}>
            <span className="block truncate text-sm">{task.source.video_url || task.text}</span>
            <span className="mt-1 block text-xs text-muted-foreground">{STATES[task.state] || task.state} · {task.elapsed} 秒 · {task.channel === "feishu" ? "飞书" : task.channel === "desktop" ? "桌面" : "视频页"}</span>
            <span className="block text-xs text-muted-foreground">{new Date(task.created * 1000).toLocaleString()}</span>
          </button>)}
        </div>
      </section>
      <section className="min-w-0 space-y-4 rounded-2xl border border-border bg-card/70 p-5" aria-label="视频任务结果">
        {!detail ? <p className="text-sm text-muted-foreground">选择一条记录查看总结与视频来源。</p> : <>
          <div className="flex items-center justify-between gap-3"><h2 className="font-medium">{STATES[detail.state] || detail.state} · {detail.elapsed} 秒</h2>
            <button className="rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-40" disabled={busy || !active(detail)}
              onClick={() => void run("cancel_agent_task", { task_id: detail.id })}>停止任务</button></div>
          {detail.error && <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{detail.error}</p>}
          <div className="rounded-lg bg-secondary/50 p-4"><Markdown text={detail.answer || "任务已登记，等待读取视频与生成总结。"} /></div>
          {!debug && <TaskVideos key={detail.id} info={info} taskId={detail.id} state={detail.state} />}
          <details><summary className="cursor-pointer text-sm">任务时间线</summary>
            <ol className="mt-3 space-y-2 text-xs text-muted-foreground">{(detail.events || []).filter(event => ["status", "tool_start", "tool_end", "failure"].includes(event.kind)).map(event =>
              <li key={event.seq}>{new Date(event.ts * 1000).toLocaleTimeString()} · {typeof event.data === "string" ? event.data : `${event.kind === "tool_start" ? "调用" : "返回"} ${event.data.tool || "工具"} ${event.data.status || ""}`}</li>)}</ol>
          </details>
          <label className="block text-sm">继续追问<textarea className="mt-2 block w-full rounded-lg border border-border bg-background p-3" rows={3}
            value={question} onChange={event => setQuestion(event.target.value)} placeholder="例如：展开讲讲 03:20 的技术细节；或重新获取这个视频的字幕。" /></label>
          <p className="text-xs text-muted-foreground">保留所选视频会话的上下文；来自飞书的任务在此追问只生成本地回答。</p>
          <button className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-40" disabled={!info || busy || debug || active(detail) || !question.trim()}
            onClick={() => void run("continue_video_task", { task_id: detail.id, text: question.trim() })}>继续追问</button>
        </>}
      </section>
    </div>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    <VideoSettings info={info} debug={debug} expanded />
  </div>;
}

type Settings = { proxy: string; cookie_file: string };
type Source = { source_id: string; title: string; author: string; url: string; platform: string;
  subtitle_notice: string; subtitle_language: string; segment_count: number; truncated: boolean;
  chapters: { title: string; start: number }[]; export_state?: string; document_url?: string };

export function VideoSettings({ info, debug = false, expanded = false }: { info: BackendInfo | null; debug?: boolean; expanded?: boolean }) {
  const [settings, setSettings] = useState<Settings>({ proxy: "", cookie_file: "" });
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (!info || debug) return;
    let live = true;
    rpc<{ settings: Settings }>(info, "load_video_settings").then(value => {
      if (live) { setSettings(value.settings); setLoaded(true); }
    }).catch(err => { if (live) setMessage(String(err)); });
    return () => { live = false; };
  }, [info, debug]);
  async function save() {
    if (!info || !loaded || busy) return;
    setBusy(true); setMessage("");
    try {
      await rpc(info, "save_video_settings", settings);
      setMessage("视频设置已保存，下次读取视频时生效。");
    } catch (err) { setMessage(String(err)); }
    finally { setBusy(false); }
  }
  return <details open={expanded || undefined} className="mt-4 rounded-lg border border-border bg-card/70 p-4">
    <summary className="cursor-pointer text-sm">视频读取设置</summary>
    <p className="mt-2 text-sm text-muted-foreground">也可在桌面对话或飞书私聊发送 Bilibili / YouTube 链接。只读取信息和字幕；没有字幕会明确提示。</p>
    <div className="mt-3 space-y-3 text-sm">
      <label className="block">网络代理（可选）<input className="mt-1 block w-full rounded border border-border bg-background p-2" value={settings.proxy}
        disabled={!loaded || busy} placeholder="例如 http://127.0.0.1:7890；留空沿用系统网络"
        onChange={e => setSettings({ ...settings, proxy: e.target.value })} /></label>
      <label className="block">字幕登录文件（可选）<input className="mt-1 block w-full rounded border border-border bg-background p-2" value={settings.cookie_file}
        disabled={!loaded || busy} placeholder="自己导出的 Netscape 格式 cookies.txt 的完整路径"
        onChange={e => setSettings({ ...settings, cookie_file: e.target.value })} /></label>
      <p className="text-xs text-muted-foreground">Bilibili 部分字幕需要登录。登录文件只供本机读取，不上传到飞书；知行不会自动读取浏览器登录信息。更改设置后，可在追问中说“重新获取这个视频”。</p>
      <button className="rounded bg-secondary px-3 py-2 disabled:opacity-40" disabled={!loaded || busy || debug} onClick={() => void save()}>保存视频设置</button>
      {message && <p role="status">{message}</p>}
    </div>
  </details>;
}

export function TaskVideos({ info, taskId, state }: { info: BackendInfo | null; taskId: string; state: string }) {
  const activeTask = useRef(taskId);
  activeTask.current = taskId;
  const [items, setItems] = useState<Source[]>([]);
  const [busy, setBusy] = useState("");
  const [saved, setSaved] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [absent, setAbsent] = useState<Record<string, boolean>>({});
  useEffect(() => {
    if (!info || !taskId) return;
    let live = true;
    let pending = false;
    setItems([]); setSaved({}); setError(""); setAbsent({});
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try {
        const value = await rpc<{ items: Source[] }>(info, "list_task_videos", { task_id: taskId });
        if (live) setItems(value.items);
      } catch (err) { if (live) setError(String(err)); }
      finally { pending = false; }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => { live = false; window.clearInterval(timer); };
  }, [info, taskId, state]);
  async function save(source: Source) {
    if (!info || busy) return;
    setBusy(source.source_id); setError("");
    try {
      const args: Record<string, unknown> = { task_id: taskId, source_id: source.source_id };
      if (source.export_state === "pending" && absent[source.source_id]) args.confirmed_absent = true;
      const result = await rpc<{ url: string }>(info, "export_task_video", args);
      if (activeTask.current === taskId) setSaved(previous => ({ ...previous, [source.source_id]: result.url }));
    } catch (err) { if (activeTask.current === taskId) setError(String(err)); }
    finally { setBusy(""); }
  }
  if (!items.length && !error) return null;
  return <section aria-label="本会话视频来源" className="rounded-lg border border-border p-3 text-sm">
    <h3>本会话视频来源</h3>
    <p className="mt-1 text-xs text-muted-foreground">可在下方继续追问。保存会将当前任务答案与所选原视频一起写入飞书文档。</p>
    {items.map(source => <div key={source.source_id} className="mt-3 rounded bg-secondary/50 p-3">
      <MdLink href={source.url}>{source.title}</MdLink>
      <p className="mt-1 text-muted-foreground">{source.platform} · {source.author || "作者未知"}</p>
      <p className="mt-1">{source.subtitle_notice} {source.segment_count > 0 && `${source.segment_count} 段 · ${source.subtitle_language}`}</p>
      {source.export_state === "pending" && !saved[source.source_id] && <label className="mt-2 block text-primary">
        上次保存结果未确认，请先检查飞书云空间。
        <span className="mt-1 block"><input type="checkbox" checked={!!absent[source.source_id]}
          onChange={e => setAbsent({ ...absent, [source.source_id]: e.target.checked })} /> 我已核实没有生成文档，允许重新保存</span>
      </label>}
      {source.chapters.length > 0 && <details className="mt-2"><summary>平台章节（{source.chapters.length}）</summary>
        <ul className="mt-2 space-y-1">{source.chapters.map((chapter, i) => <li key={i}>{Math.floor(chapter.start / 60)}:{String(Math.floor(chapter.start % 60)).padStart(2, "0")} · {chapter.title}</li>)}</ul>
      </details>}
      <button className="mt-2 rounded bg-secondary px-3 py-2 disabled:opacity-40" disabled={!!busy || state !== "succeeded" || (source.export_state === "pending" && !absent[source.source_id])}
        onClick={() => void save(source)}>{busy === source.source_id ? "正在保存…" : "保存当前答案到飞书文档"}</button>
      {(saved[source.source_id] || source.document_url) && <MdLink href={saved[source.source_id] || source.document_url}>打开视频笔记</MdLink>}
    </div>)}
    {error && <p className="mt-2 text-destructive" role="alert">{error}</p>}
  </section>;
}
