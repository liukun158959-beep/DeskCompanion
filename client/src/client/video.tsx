import { useEffect, useRef, useState } from "react";
import { rpc, type BackendInfo } from "./api";
import { MdLink } from "./Markdown";

type Settings = { proxy: string; cookie_file: string };
type Source = { source_id: string; title: string; author: string; url: string; platform: string;
  subtitle_notice: string; subtitle_language: string; segment_count: number; truncated: boolean;
  chapters: { title: string; start: number }[]; export_state?: string; document_url?: string };

export function VideoSettings({ info, debug = false }: { info: BackendInfo | null; debug?: boolean }) {
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
  return <details className="mt-4 rounded-lg border border-white/10 p-3">
    <summary className="cursor-pointer text-sm">视频读取设置</summary>
    <p className="mt-2 text-sm text-white/50">在桌面对话或飞书私聊发送 Bilibili / YouTube 链接即可总结。只读取信息和字幕；没有字幕会明确提示。</p>
    <div className="mt-3 space-y-3 text-sm">
      <label className="block">网络代理（可选）<input className="mt-1 block w-full rounded bg-white/10 p-2" value={settings.proxy}
        disabled={!loaded || busy} placeholder="例如 http://127.0.0.1:7890；留空沿用系统网络"
        onChange={e => setSettings({ ...settings, proxy: e.target.value })} /></label>
      <label className="block">字幕登录文件（可选）<input className="mt-1 block w-full rounded bg-white/10 p-2" value={settings.cookie_file}
        disabled={!loaded || busy} placeholder="自己导出的 Netscape 格式 cookies.txt 的完整路径"
        onChange={e => setSettings({ ...settings, cookie_file: e.target.value })} /></label>
      <p className="text-xs text-white/40">Bilibili 部分字幕需要登录。登录文件只供本机读取，不上传到飞书；知行不会自动读取浏览器登录信息。更改设置后，可在对话里说“重新获取这个视频”。</p>
      <button className="rounded bg-white/10 px-3 py-2" disabled={!loaded || busy || debug} onClick={() => void save()}>保存视频设置</button>
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
  return <section aria-label="本会话视频来源" className="rounded-lg border border-white/10 p-3 text-sm">
    <h3>本会话视频来源</h3>
    <p className="mt-1 text-xs text-white/40">可在下方继续追问。保存会将当前任务答案与所选原视频一起写入飞书文档。</p>
    {items.map(source => <div key={source.source_id} className="mt-3 rounded bg-white/5 p-3">
      <MdLink href={source.url}>{source.title}</MdLink>
      <p className="mt-1 text-white/50">{source.platform} · {source.author || "作者未知"}</p>
      <p className="mt-1">{source.subtitle_notice} {source.segment_count > 0 && `${source.segment_count} 段 · ${source.subtitle_language}`}</p>
      {source.export_state === "pending" && !saved[source.source_id] && <label className="mt-2 block text-amber-200">
        上次保存结果未确认，请先检查飞书云空间。
        <span className="mt-1 block"><input type="checkbox" checked={!!absent[source.source_id]}
          onChange={e => setAbsent({ ...absent, [source.source_id]: e.target.checked })} /> 我已核实没有生成文档，允许重新保存</span>
      </label>}
      {source.chapters.length > 0 && <details className="mt-2"><summary>平台章节（{source.chapters.length}）</summary>
        <ul className="mt-2 space-y-1">{source.chapters.map((chapter, i) => <li key={i}>{Math.floor(chapter.start / 60)}:{String(Math.floor(chapter.start % 60)).padStart(2, "0")} · {chapter.title}</li>)}</ul>
      </details>}
      <button className="mt-2 rounded bg-white/10 px-3 py-2" disabled={!!busy || state !== "succeeded" || (source.export_state === "pending" && !absent[source.source_id])}
        onClick={() => void save(source)}>{busy === source.source_id ? "正在保存…" : "保存当前答案到飞书文档"}</button>
      {(saved[source.source_id] || source.document_url) && <MdLink href={saved[source.source_id] || source.document_url}>打开视频笔记</MdLink>}
    </div>)}
    {error && <p className="mt-2 text-red-300" role="alert">{error}</p>}
  </section>;
}
