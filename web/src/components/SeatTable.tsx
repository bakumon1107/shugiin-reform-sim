"use client";

import { Delta } from "./Delta";

/**
 * 党派別の議席比較。
 *
 * 政党の識別は行ラベルが担い、色は「量」（青の一色バー）と「増減の向き」だけに
 * 使う。政党数は選挙回によって14を超えるので、識別のために色を配ると必ず
 * 見分けのつかない組み合わせが出る。
 */
export function SeatTable({
  baseline,
  proposal,
  proposalName,
  totalSeats,
}: {
  baseline: Record<string, number>;
  proposal: Record<string, number>;
  proposalName: string;
  /** 案のもとでの法定定数（欠員を含む） */
  totalSeats: number;
}) {
  const parties = [...new Set([...Object.keys(baseline), ...Object.keys(proposal)])].sort(
    (a, b) => (proposal[b] ?? 0) - (proposal[a] ?? 0) || (baseline[b] ?? 0) - (baseline[a] ?? 0)
  );
  const max = Math.max(...parties.map((p) => Math.max(baseline[p] ?? 0, proposal[p] ?? 0)), 1);
  const baseTotal = Object.values(baseline).reduce((a, b) => a + b, 0);
  const propTotal = Object.values(proposal).reduce((a, b) => a + b, 0);

  return (
    <div className="scroll-x">
      <table className="w-full min-w-[560px] border-collapse text-[13px]">
        <thead>
          <tr style={{ color: "var(--ink-muted)" }} className="text-left">
            <th className="w-[26%] py-2 pr-3 font-medium">党派</th>
            <th className="w-[13%] py-2 pr-3 text-right font-medium">現行</th>
            <th className="w-[13%] py-2 pr-3 text-right font-medium">{proposalName}</th>
            <th className="w-[11%] py-2 pr-4 text-right font-medium">増減</th>
            <th className="py-2 font-medium">議席（現行＝細線／案＝バー）</th>
          </tr>
        </thead>
        <tbody>
          {parties.map((party) => {
            const b = baseline[party] ?? 0;
            const p = proposal[party] ?? 0;
            return (
              <tr key={party} style={{ borderTop: "1px solid var(--grid)" }}>
                <td className="py-2 pr-3">{party}</td>
                <td className="tnum py-2 pr-3 text-right" style={{ color: "var(--ink-2)" }}>
                  {b}
                </td>
                <td className="tnum py-2 pr-3 text-right font-semibold">{p}</td>
                <td className="py-2 pr-4 text-right">
                  <Delta value={p - b} />
                </td>
                <td className="py-2">
                  <div className="relative h-5" title={`現行 ${b} → ${proposalName} ${p}`}>
                    {/* 案の議席＝塗りバー。データ端だけ丸める。 */}
                    <div
                      className="absolute top-1 h-3"
                      style={{
                        width: `${(p / max) * 100}%`,
                        background: "var(--bar-450)",
                        borderRadius: "0 4px 4px 0",
                      }}
                    />
                    {/* 現行の議席＝基準線 */}
                    <div
                      className="absolute top-0 h-5 w-0.5"
                      style={{ left: `${(b / max) * 100}%`, background: "var(--ink-2)" }}
                    />
                  </div>
                </td>
              </tr>
            );
          })}
          <tr style={{ borderTop: "2px solid var(--axis)" }}>
            <td className="py-2 pr-3 font-semibold">議員数の合計</td>
            <td className="tnum py-2 pr-3 text-right" style={{ color: "var(--ink-2)" }}>
              {baseTotal}
            </td>
            <td className="tnum py-2 pr-3 text-right font-semibold">{propTotal}</td>
            <td className="py-2 pr-4 text-right">
              <Delta value={propTotal - baseTotal} />
            </td>
            <td className="py-2 text-[12px]" style={{ color: "var(--ink-muted)" }}>
              {propTotal === totalSeats
                ? `法定定数 ${totalSeats}`
                : `法定定数 ${totalSeats}（うち欠員 ${totalSeats - propTotal}）`}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
