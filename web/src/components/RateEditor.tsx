"use client";

import type { Personas } from "@/sim/types";

/**
 * 拒否率を読み手が自分で動かせるようにする。
 *
 * 優先順位付投票の議席数は、この数字が決めている。仮定を隠して1つの答えを出すより、
 * 読み手に握らせて動かしてもらうほうが正直だと考えている。動かすと選好順序も層も
 * 作り直され、議席がその場で計算し直される。
 *
 * 元の値は公開されたグラフからの目視読み取りで ±2 ポイント程度の誤差があるため、
 * 刻みも 5% にしてある。それより細かく動かせても意味のある精度にならない。
 */
const STEP = 5;

export function RateEditor({
  personas,
  overrides,
  onChange,
  onReset,
}: {
  personas: Personas;
  /** 読み手が動かした値。政党 → 拒否対象 → % */
  overrides: Record<string, Record<string, number>>;
  onChange: (voter: string, target: string, rate: number) => void;
  onReset: () => void;
}) {
  const parties = Object.keys(personas.rejectionRates);
  const edited = Object.keys(overrides);
  const rateOf = (voter: string, target: string) =>
    overrides[voter]?.[target] ?? personas.rejectionRates[voter][target];

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-2xl text-[12px]" style={{ color: "var(--ink-2)" }}>
          「その政党に投じた人のうち、何%が相手を<strong>絶対投票したくない</strong>と
          答えたか」です。動かすと選好順序と有権者の層が作り直され、議席がその場で
          計算し直されます。{STEP}%刻みなのは、元の値が目視の読み取りで
          ±2ポイントの誤差を持つためです。
        </p>
        {edited.length > 0 && (
          <button
            type="button"
            onClick={onReset}
            className="rounded-lg px-3 py-1.5 text-[12px]"
            style={{ border: "1px solid var(--hairline)", color: "var(--ink-2)" }}
          >
            元の値に戻す（{edited.length}党を編集中）
          </button>
        )}
      </div>

      <div className="mt-3 scroll-x">
        <table className="w-full min-w-[760px] border-collapse text-[12px]">
          <caption className="mb-1 text-left text-[11px]" style={{ color: "var(--ink-muted)" }}>
            行＝比例投票先、列＝拒否された政党。数字が大きいほど強く拒否されている。
          </caption>
          <thead>
            <tr style={{ color: "var(--ink-muted)" }}>
              <th className="py-1.5 pr-2 text-left font-medium">投票先＼拒否</th>
              {parties.map((p) => (
                <th key={p} className="px-1 py-1.5 text-center font-medium">
                  <span className="inline-block max-w-[52px] truncate" title={p}>
                    {p}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {parties.map((voter) => (
              <tr key={voter} style={{ borderTop: "1px solid var(--grid)" }}>
                <th
                  className="py-1 pr-2 text-left font-normal whitespace-nowrap"
                  style={{ color: voter in personas.derived ? "var(--warning)" : "var(--ink)" }}
                  title={personas.derived[voter]}
                >
                  {voter}
                  {voter in personas.derived && "※"}
                </th>
                {parties.map((target) => {
                  const v = rateOf(voter, target);
                  const changed = overrides[voter]?.[target] !== undefined;
                  return (
                    <td key={target} className="px-0.5 py-1 text-center">
                      <input
                        type="number"
                        min={0}
                        max={100}
                        step={STEP}
                        value={v}
                        onChange={(e) => {
                          const n = Math.min(100, Math.max(0, Number(e.target.value)));
                          onChange(voter, target, n);
                        }}
                        aria-label={`${voter}に投じた人のうち${target}を拒否する割合`}
                        className="tnum w-12 rounded px-1 py-0.5 text-center"
                        style={{
                          border: `1px solid ${changed ? "var(--gain)" : "var(--hairline)"}`,
                          background: "var(--surface)",
                          color: changed ? "var(--gain)" : "var(--ink-2)",
                          // 拒否率が高いほど濃く見えるようにして、傾向を目で追えるようにする
                          boxShadow: `inset 0 0 0 999px color-mix(in srgb, var(--loss) ${
                            Math.round(v * 0.35)
                          }%, transparent)`,
                        }}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-2 text-[11px]" style={{ color: "var(--ink-muted)" }}>
        ※ の政党は調査に出てこないため、近い政党から派生させた想定です。
        無所属は手がかりが無いので表に入れていません（落ちた票は残る候補へ均等に割ります）。
      </p>
    </div>
  );
}
