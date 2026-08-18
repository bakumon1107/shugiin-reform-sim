import { Delta } from "./Delta";

export type Tile = {
  label: string;
  value: string;
  delta?: number;
  note?: string;
};

/** 見出しの数字。数字が主役なのでグラフにはしない。 */
export function StatTiles({ tiles }: { tiles: Tile[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {tiles.map((t) => (
        // 「第1党（減税日本・ゆうこく連合）の議席率」のように見出しが長くなるので、
        // 狭い画面でも折り返して収まるようにしておく。
        <div key={t.label} className="card min-w-0 px-4 py-3">
          <div className="text-[12px] break-all" style={{ color: "var(--ink-muted)" }}>
            {t.label}
          </div>
          <div className="mt-1 flex flex-wrap items-baseline gap-x-2">
            <span className="text-[26px] leading-none font-semibold">{t.value}</span>
            {t.delta !== undefined && <Delta value={t.delta} />}
          </div>
          {t.note && (
            <div className="mt-1 text-[11px] break-all" style={{ color: "var(--ink-muted)" }}>
              {t.note}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
