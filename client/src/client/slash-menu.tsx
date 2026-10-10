import { useEffect, useRef } from "react";
import { LoadingText } from "./loading-text";

export type SlashSkill = { id: string; label: string; description?: string };
export type SlashTool = { id: string; label: string };
export type SlashRepo = { id: string; label: string };

export type ComposerOptions = {
  ok: boolean;
  error?: string;
  skills: SlashSkill[];
  cli: SlashTool[];
  github: { ok: boolean; error?: string; items: SlashRepo[] };
};

export const NEED_REPO = new Set(["github_recent", "github_roadmap"]);

export const MCP_SEP = "\u001f";

export type SlashParent = "all" | "skill" | "tool" | "doc" | "mcp" | "attachment";

export const SLASH_PARENTS: { id: SlashParent; label: string }[] = [
  { id: "all", label: "全部" },
  { id: "skill", label: "技能" },
  { id: "tool", label: "工具" },
  { id: "doc", label: "飞书文档" },
  { id: "mcp", label: "MCP" },
  { id: "attachment", label: "附件" },
];

export type SlashItem = { id: string; label: string; description?: string; parent?: SlashParent; source?: string; picked?: boolean };

export function slashQuery(draft: string): string | null {
  const match = draft.match(/(?:^|\s)\/([^\s/]*)$/);
  if (!match) return null;
  return match[1];
}

export function stripSlash(draft: string): string {
  return draft.replace(/(?:^|\s)\/[^\s/]*$/, "").trim();
}

export function filterSlash(items: SlashItem[], query: string): SlashItem[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return items;
  return items.filter((item) => {
    const description = item.description || "";
    return (
      item.id.toLowerCase().includes(needle) ||
      item.label.toLowerCase().includes(needle) ||
      description.toLowerCase().includes(needle)
    );
  });
}

export function SlashMenu(props: {
  open: boolean;
  parent: SlashParent;
  repoPicking: boolean;
  items: SlashItem[];
  active: number;
  error: string;
  loading: boolean;
  onParent: (parent: SlashParent) => void;
  onPick: (id: string, parent?: SlashParent) => void;
  onClose: () => void;
  onBack: () => void;
  onRetry: () => void;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const panel = panelRef.current;
    const form = panel?.parentElement?.querySelector("form");
    if (!panel || !form) return;
    const position = () => {
      const height = panel.parentElement!.getBoundingClientRect().bottom - form.getBoundingClientRect().top + 8;
      panel.style.bottom = `${height}px`;
      panel.style.maxHeight = `max(120px,min(360px,calc(100cqh - ${height + 20}px)))`;
    };
    position(); const observer = new ResizeObserver(position); observer.observe(form); observer.observe(panel.parentElement!);
    return () => observer.disconnect();
  }, [props.open]);
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const selected = list.querySelector("[data-selected='1']");
    if (!(selected instanceof HTMLElement)) return;
    const row = selected.getBoundingClientRect(), box = list.getBoundingClientRect();
    if (row.top < box.top) list.scrollTop -= box.top - row.top;
    else if (row.bottom > box.bottom) list.scrollTop += row.bottom - box.bottom;
  }, [props.active, props.items, props.parent, props.open]);

  if (!props.open) return null;
  return (
    <div
      ref={panelRef}
      data-slash-menu=""
      data-slash-repo={props.repoPicking ? "1" : "0"}
      data-slash-radius="10"
      className="slash-menu"
    >
      <header className="slash-header"><span>{props.repoPicking ? "选择仓库 · 完成后加入工具" : "选择本轮技能、工具与资料"}</span><div>{props.repoPicking && <button type="button" className="desk-menu-item" onClick={props.onBack}>← 返回</button>}<button type="button" className="desk-menu-item" aria-label="关闭斜杠菜单" onClick={props.onClose}>×</button></div></header>
      <div className="slash-body">
        <nav className="slash-categories" aria-label="菜单分类">
          {SLASH_PARENTS.map((item) => (
            <button
              key={item.id}
              type="button"
              data-slash-parent={item.id}
              data-selected={props.parent === item.id ? "1" : "0"}
              aria-pressed={props.parent === item.id}
              className={`block w-full px-3 py-2 text-left hover:bg-secondary ${
                props.parent === item.id ? "bg-primary/15 text-primary" : "text-muted-foreground"
              }`}
              onMouseDown={(ev) => ev.preventDefault()}
              onClick={() => props.onParent(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div ref={listRef} data-slash-list="" className="slash-list">
          {props.repoPicking ? (
            <div className="px-3 py-2 text-xs text-muted-foreground">选择仓库</div>
          ) : null}
          {props.error ? (
            <p data-slash-error className="px-3 py-2 text-destructive">
              {props.error}<button className="desk-menu-item" type="button" onClick={props.onRetry}>重新读取</button>
            </p>
          ) : null}
          {props.loading ? (
            <p className="px-3 py-2 text-muted-foreground" role="status"><LoadingText text="正在读取菜单项目…" /></p>
          ) : null}
          {!props.error && !props.loading && props.items.length === 0 ? (
            <p className="px-3 py-2 text-muted-foreground">没有匹配。</p>
          ) : null}
          {props.items.map((item, index) => (
            <button
              key={`${item.parent || props.parent}:${item.id}`}
              type="button"
              data-slash-item=""
              data-slash-id={item.id}
              data-selected={index === props.active ? "1" : "0"}
              className={`slash-item hover:bg-secondary ${
                index === props.active ? "bg-primary/15 text-primary" : ""
              }`}
              onMouseDown={(ev) => ev.preventDefault()}
              onClick={() => props.onPick(item.id, item.parent)}
            >
              <span className="slash-item-title">{item.label}{item.picked && <span className="slash-picked">✓ 已加入</span>}</span>
              {item.description ? (
                <span className="slash-description">{item.description}</span>
              ) : null}
              {item.source && <span className="slash-source">{item.source}</span>}
            </button>
          ))}
        </div>
      </div>
      <p data-slash-hint className="shrink-0 border-t border-border px-3 py-1.5 text-xs text-muted-foreground">
        Alt + ← → 切换分类 · ↑ ↓ 移动 · 回车选中 · Esc {props.repoPicking ? "返回" : "关闭"}
      </p>
    </div>
  );
}
