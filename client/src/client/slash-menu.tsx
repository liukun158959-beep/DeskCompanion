import { useEffect, useRef } from "react";

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

export type SlashParent = "skill" | "tool" | "doc" | "mcp" | "attachment";

export const SLASH_PARENTS: { id: SlashParent; label: string }[] = [
  { id: "skill", label: "技能" },
  { id: "tool", label: "已注册工具" },
  { id: "doc", label: "飞书文档" },
  { id: "mcp", label: "MCP" },
  { id: "attachment", label: "附件" },
];

export type SlashItem = { id: string; label: string; description?: string };

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
  onPick: (id: string) => void;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const selected = list.querySelector("[data-selected='1']");
    if (!(selected instanceof HTMLElement)) return;
    const top = selected.offsetTop;
    const bottom = top + selected.offsetHeight;
    if (top < list.scrollTop) list.scrollTop = top;
    else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight;
  }, [props.active, props.items, props.parent, props.open]);

  if (!props.open) return null;
  return (
    <div
      data-slash-menu=""
      data-slash-repo={props.repoPicking ? "1" : "0"}
      data-slash-radius="10"
      className="mb-2 flex h-52 shrink-0 flex-col overflow-hidden rounded-[10px] border border-border bg-card text-sm"
    >
      <div className="flex min-h-0 flex-1">
        <div className="w-36 min-h-0 shrink-0 overflow-y-auto border-r border-border">
          {SLASH_PARENTS.map((item) => (
            <button
              key={item.id}
              type="button"
              data-slash-parent={item.id}
              data-selected={props.parent === item.id ? "1" : "0"}
              className={`block w-full px-3 py-2 text-left hover:bg-secondary ${
                props.parent === item.id ? "bg-primary/15 text-primary" : "text-muted-foreground"
              }`}
              onMouseDown={(ev) => ev.preventDefault()}
              onClick={() => props.onParent(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div ref={listRef} data-slash-list="" className="relative min-h-0 min-w-0 flex-1 overflow-y-auto">
          {props.repoPicking ? (
            <div className="px-3 py-2 text-xs text-muted-foreground">选择仓库</div>
          ) : null}
          {props.error ? (
            <p data-slash-error className="px-3 py-2 text-destructive">
              {props.error}
            </p>
          ) : null}
          {!props.error && props.loading ? (
            <p className="px-3 py-2 text-muted-foreground">正在读取。</p>
          ) : null}
          {!props.error && !props.loading && props.items.length === 0 ? (
            <p className="px-3 py-2 text-muted-foreground">没有匹配。</p>
          ) : null}
          {props.items.map((item, index) => (
            <button
              key={item.id}
              type="button"
              data-slash-item=""
              data-slash-id={item.id}
              data-selected={index === props.active ? "1" : "0"}
              className={`block w-full px-3 py-2 text-left hover:bg-secondary ${
                index === props.active ? "bg-primary/15 text-primary" : ""
              }`}
              onMouseDown={(ev) => ev.preventDefault()}
              onClick={() => props.onPick(item.id)}
            >
              <span>{item.label}</span>
              {item.description ? (
                <span className="ml-2 text-xs text-muted-foreground">{item.description}</span>
              ) : null}
            </button>
          ))}
        </div>
      </div>
      <p data-slash-hint className="shrink-0 border-t border-border px-3 py-1.5 text-xs text-muted-foreground">
        ← → 切换技能、工具、飞书文档、MCP、附件 · ↑ ↓ 移动 · 回车选中 · Esc 关闭
      </p>
    </div>
  );
}
