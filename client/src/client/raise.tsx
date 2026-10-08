import { useState } from "react";

export type RaiseTarget = {
  operator: string;
  rank: string;
};

export type RaiseLine = {
  name: string;
  tier: number | null;
  need: number;
  have: number;
  in_depot: boolean;
  short: number;
};

export type RaisePayload = {
  ok?: boolean;
  error?: string;
  roster?: RaiseTarget[];
  depot_day?: string;
  lines?: RaiseLine[];
};

export function RaisePane(props: {
  data: RaisePayload | null;
  loading: boolean;
  formError: string;
  busy: boolean;
  onAdd: (operator: string, rank: string) => void;
  onRemove: (operator: string, rank: string) => void;
}) {
  const data = props.data;
  const failed = !data || data.ok === false;
  const roster = data?.roster || [];
  const lines = failed ? [] : data?.lines || [];
  const [name, setName] = useState("");
  const [rank, setRank] = useState("精一");

  return (
    <div data-raise data-raise-ok={data ? (failed ? "0" : "1") : ""}>
      <div className="mb-6">
        <h1 className="text-xl font-semibold">培养</h1>
        <div className="mt-1 text-sm text-muted-foreground">点名要养的干员，看升到这一档还缺多少</div>
      </div>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(ev) => {
          ev.preventDefault();
          props.onAdd(name.trim(), rank);
        }}
      >
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">干员</span>
          <input
            data-raise-name
            value={name}
            onChange={(ev) => setName(ev.target.value)}
            className="border border-border bg-card px-3 py-2"
          />
        </label>
        <div className="flex gap-2 text-sm">
          {["精一", "精二"].map((item) => (
            <button
              key={item}
              type="button"
              data-raise-rank={item}
              data-selected={rank === item ? "1" : "0"}
              onClick={() => setRank(item)}
              className={rank === item ? "desk-btn desk-btn-lg desk-btn-solid" : "desk-btn desk-btn-lg"}
            >
              {item}
            </button>
          ))}
        </div>
        <button type="submit" data-raise-add disabled={props.busy} className="desk-btn desk-btn-lg desk-btn-solid">
          加入
        </button>
      </form>
      <p className="mt-2 text-xs text-muted-foreground">精一、精二只算升到这一档的晋升消耗，不含技能升级、专精、模组，也不含另一档。</p>
      {props.formError ? <p data-raise-form-error className="mt-3 text-sm text-destructive">{props.formError}</p> : null}
      <ul className="mt-6 space-y-2">
        {roster.map((item) => (
          <li key={`${item.operator}-${item.rank}`} data-raise-target data-name={item.operator} data-rank={item.rank} className="flex items-center justify-between border border-border px-3 py-2 text-sm">
            <span>{item.operator} {item.rank}</span>
            <button type="button" data-raise-remove onClick={() => props.onRemove(item.operator, item.rank)} className="desk-btn desk-btn-danger">
              移除
            </button>
          </li>
        ))}
      </ul>
      {props.loading ? <p className="mt-6 text-sm text-muted-foreground">正在算缺口…</p> : null}
      {failed && data?.error ? <p data-raise-error className="mt-6 text-sm leading-6 text-destructive">{data.error}</p> : null}
      {!failed && data?.depot_day ? (
        <p data-raise-sync data-raise-day={data.depot_day} className="mt-6 text-sm text-muted-foreground">
          仓库日期 {data.depot_day}
        </p>
      ) : null}
      {lines.length > 0 ? (
        <ul className="mt-4 space-y-3">
          {lines.map((line) => (
            <li
              key={line.name}
              data-raise-line
              data-name={line.name}
              data-need={line.need}
              data-have={line.in_depot ? line.have : ""}
              data-short={line.short}
              data-recorded={line.in_depot ? "1" : "0"}
              className="border border-border bg-card/80 px-3 py-2 text-sm"
            >
              <div>{line.name}{line.tier === null ? "" : ` 阶级 ${line.tier}`}</div>
              <div className="mt-1 tabular-nums text-muted-foreground">
                需要 {line.need} · {line.in_depot ? `仓库 ${line.have}` : "仓库未记录，按 0"} · 缺口 {line.short}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
