import { useState } from "react";
import type { BackendInfo } from "./api";

export type DepotItem = {
  id: string;
  name: string;
  tier: number | null;
  count: number;
  icon_id: string | null;
  icon?: string;
};

export type DepotGroup = {
  id: string;
  label: string;
  items: DepotItem[];
};

export type DepotPayload = {
  ok?: boolean;
  error?: string;
  depot_sync?: string;
  depot_day?: string;
  today?: boolean;
  count?: number;
  groups?: DepotGroup[];
};

export function DepotPane(props: { data: DepotPayload | null; loading: boolean; info: BackendInfo | null }) {
  const data = props.data;
  const failed = data?.ok === false;
  const groups = failed ? [] : data?.groups || [];
  return (
    <div data-depot data-depot-ok={failed ? "0" : data ? "1" : ""}>
      <div className="mb-6">
        <h1 className="text-xl font-semibold">仓库</h1>
        <div className="mt-1 text-sm text-muted-foreground">扫到的材料</div>
      </div>
      {props.loading ? <p className="text-sm text-muted-foreground">正在读仓库…</p> : null}
      {failed ? <p data-depot-error className="text-sm leading-6 text-destructive">{data?.error || "读取仓库失败。"}</p> : null}
      {!failed && data?.depot_day ? (
        <p
          data-depot-sync
          data-depot-day={data.depot_day}
          data-depot-today={data.today ? "1" : "0"}
          className={data.today ? "text-sm text-muted-foreground" : "text-sm text-destructive"}
        >
          仓库日期 {data.depot_day}
          {data.today ? "" : "，不是今天"}
          {typeof data.count === "number" ? ` · ${data.count} 件` : ""}
        </p>
      ) : null}
      {!failed && data && groups.length === 0 && !props.loading ? (
        <p data-depot-empty className="mt-4 text-sm text-muted-foreground">
          {data.today === false ? "这份仓库没有材料。" : "今天的仓库没有材料。"}
        </p>
      ) : null}
      <div className="mt-6 space-y-8">
        {groups.map((group) => (
          <section key={group.id} data-depot-group={group.id}>
            <h2 className="text-xs text-muted-foreground">{group.label}</h2>
            <div className="mt-3 grid grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))] gap-3">
              {group.items.map((item) => (
                <DepotCell key={`${group.id}-${item.name}`} item={item} info={props.info} group={group.id} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function DepotCell(props: { item: DepotItem; info: BackendInfo | null; group: string }) {
  const [broken, setBroken] = useState(false);
  const src = broken ? "" : iconUrl(props.item, props.info);
  const tier = props.item.tier;
  return (
    <article
      data-depot-item
      data-name={props.item.name}
      data-count={props.item.count}
      data-group={props.group}
      data-tier={tier === null ? "" : String(tier)}
      data-icon={src ? "1" : "0"}
      className="border border-border bg-card/80 p-3"
    >
      {src ? (
        <img
          src={src}
          alt=""
          width={48}
          height={48}
          className="h-12 w-12 object-contain"
          onError={() => setBroken(true)}
        />
      ) : (
        <div className="flex h-12 w-12 items-center justify-center border border-border text-[10px] text-muted-foreground">
          缺图标
        </div>
      )}
      <div className="mt-2 truncate text-sm">{props.item.name}</div>
      {tier !== null ? <div className="text-xs text-muted-foreground">阶级 {tier}</div> : null}
      <div className="mt-1 text-sm font-semibold tabular-nums">{props.item.count}</div>
    </article>
  );
}

function iconUrl(item: DepotItem, info: BackendInfo | null): string {
  if (item.icon) return item.icon;
  if (!item.icon_id || !info) return "";
  const token = encodeURIComponent(info.token);
  return `http://127.0.0.1:${info.port}/depot-icon/${item.icon_id}?token=${token}`;
}
